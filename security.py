"""
security.py — System Safety Guardrails for KlyroCLI
Intercepts dangerous shell commands and enforces sandbox/file-safety boundaries.

DESIGN NOTE: check_command_safety() is a best-effort DENYLIST used only to
decide the WARNING WORDING shown to the user. It is intentionally NOT the
sole gate for execution — a denylist of regex patterns can never enumerate
every dangerous command an LLM might generate (obfuscation, env var
indirection, piped interpreters, etc. all bypass it trivially).
The actual safety boundary is CONFIRM_ALL_AI_SHELL in klyro_cli.py, which
requires explicit user confirmation for every AI-issued shell command,
not just ones matching a known-bad pattern. Treat this list as "extra loud
warning for especially catastrophic patterns", not as a security control
on its own.
"""

import re
import os

# Patterns of commands that could cause severe system damage or data loss.
# Matching here upgrades the confirmation prompt to a louder warning —
# it does NOT gate whether confirmation happens at all (see design note above).
DANGEROUS_COMMAND_PATTERNS = [
    # Recursive directory/file wipes
    (r"\brm\s+-[rRfF]+", "Recursive file/directory deletion"),
    (r"\bdel\s+/[sfqSFQ]+", "Windows recursive deletion"),
    (r"\brd\s+/[sqSQ]+", "Windows recursive directory removal"),
    (r"\brmdir\s+/[sqSQ]+", "Windows recursive rmdir"),
    (r"\bfind\s+.*-delete\b", "find with -delete (bulk removal)"),
    # Disk formatting / partitioning
    (r"\bformat\s+[A-Za-z]:", "Drive formatting"),
    (r"\bmkfs\b", "Filesystem creation/format"),
    (r"\bfdisk\b", "Disk partition utility"),
    (r"\bdiskpart\b", "Windows disk partition utility"),
    # Destructive overwrites
    (r">\s*/dev/sd[a-z]", "Direct raw block device write"),
    (r">\s*/dev/nvme", "Direct NVMe drive write"),
    (r"\bdd\s+if=.*of=", "Raw disk write with dd"),
    # Dangerous system control / shutdown
    (r"\bshutdown\s+-[shrf]", "System shutdown/reboot command"),
    (r"\binit\s+0\b", "System halt"),
    (r"\btaskkill\s+/F\s+/T\s*(?!.*PID)", "Bulk process kill"),
    # Permission destruction
    (r"\bchmod\s+-[rRfF]*\s+777\b", "Unsafe global permission assignment"),
    (r"\bicacls\b.*\bgrant\b.*\bEveryone\b", "Unsafe global ACL grant"),
    # Remote code execution / pipe-to-shell patterns
    (r"(curl|wget)\s+.*\|\s*(sh|bash|powershell|cmd)\b", "Remote script piped directly into a shell"),
    (r"\biex\s*\(", "PowerShell Invoke-Expression (arbitrary remote code)"),
    # Credential / secrets exfiltration hints
    (r"\bcat\s+.*\.env\b.*\|", "Piping a secrets/.env file to another command"),
    (r"\benv\s*\|\s*(curl|wget|nc)\b", "Environment dump piped to a network tool"),
    # Git history destruction
    (r"\bgit\s+push\s+.*--force\b", "Force-push (can overwrite remote history)"),
    (r"\bgit\s+reset\s+--hard\b", "Hard reset (discards uncommitted work)"),
]


def check_command_safety(command_str: str) -> tuple[bool, str]:
    """
    Check if a shell command matches a KNOWN especially-dangerous pattern.
    Returns: (is_dangerous: bool, risk_reason: str)

    NOTE: a False result does NOT mean the command is safe — it only means
    it didn't match one of the extra-loud patterns above. Callers must still
    confirm with the user before running ANY AI-issued shell command; see
    the design note at the top of this file.
    """
    if not command_str:
        return False, ""

    cmd_normalized = command_str.strip()

    for pattern, reason in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, cmd_normalized, re.IGNORECASE):
            return True, reason

    return False, ""


def is_binary_or_media_file(filename: str) -> bool:
    """Check if file is a compiled binary, media, or archive that should not be fed to LLM."""
    BLOCKED_EXTENSIONS = {
        ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".img",
        ".zip", ".tar", ".gz", ".7z", ".rar",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
        ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav",
        ".pdf", ".docx", ".xlsx", ".pptx",
        ".sqlite", ".db", ".pyc", ".pyd"
    }
    _, ext = os.path.splitext(filename)
    return ext.lower() in BLOCKED_EXTENSIONS


# ─────────────────────────────────────────────────────────────
# INTERACTIVE COMMAND HANG BLOCKER
# ─────────────────────────────────────────────────────────────

INTERACTIVE_COMMAND_PATTERNS = [
    # Terminal editors
    (r"^\s*(?:vim|vi|nano|emacs|pico|notepad)(?:\.exe)?\b", "Interactive text editor requires user TTY; use file edit tools instead"),
    # Pagers
    (r"(?:^\s*|\b\|\s*)(?:less|more)(?:\.exe)?\b", "Interactive pager requires TTY; use head/tail or cat/type instead"),
    # Git interactive commands
    (r"^\s*git\s+commit\b(?![^#\n]*\s(?:-m|--message|-F|--file|-C|--reuse-message|-c))\b", "git commit without '-m' message requires interactive editor; use 'git commit -m \"...\"'"),
    (r"^\s*git\s+add\s+(?:-i|--interactive|-p|--patch)\b", "git interactive staging requires user TTY"),
    (r"^\s*git\s+rebase\s+(?:-i|--interactive)\b", "git interactive rebase requires user TTY"),
    # Raw interactive interpreters without script or command flag
    (r"^\s*(?:python|python3|py)(?:\.exe)?\s*$", "Interactive Python REPL requires TTY; provide a script file or use -c \"...\""),
    (r"^\s*(?:node|nodejs)(?:\.exe)?\s*$", "Interactive Node REPL requires TTY; provide a script file or use -e \"...\""),
    (r"^\s*(?:bash|sh|zsh|cmd|powershell|pwsh)(?:\.exe)?\s*$", "Interactive shell without command flag requires TTY"),
    # Database interactive shells
    (r"^\s*(?:mysql|psql|sqlite3|mongosh|mongo)(?:\.exe)?\s*$", "Interactive database client requires TTY; supply queries via flags or scripts"),
    # Package manager interactive initializers
    (r"^\s*(?:npm|yarn|pnpm)\s+init\s*$", "Interactive package init requires TTY; use flag '-y' / '--yes'"),
    # Remote interactive sessions
    (r"^\s*(?:ssh|telnet|ftp|sftp)\b", "Interactive remote session requires TTY"),
]


def check_interactive_command(command_str: str) -> tuple[bool, str]:
    """
    Checks if a shell command requires an interactive terminal / TTY,
    which would hang an automated CLI agent session.
    Returns: (is_interactive: bool, remedy_explanation: str)
    """
    if not command_str:
        return False, ""

    cmd_clean = command_str.strip()
    for pattern, reason in INTERACTIVE_COMMAND_PATTERNS:
        if re.search(pattern, cmd_clean, re.IGNORECASE):
            return True, reason
    return False, ""


# ─────────────────────────────────────────────────────────────
# SECRET & CREDENTIAL REDACTION GUARD
# ─────────────────────────────────────────────────────────────

SECRET_PATTERNS = [
    (
        "Private Key",
        re.compile(r"-----BEGIN [A-Z0-9 _-]+KEY-----[\s\S]+?-----END [A-Z0-9 _-]+KEY-----"),
        "[REDACTED_PRIVATE_KEY]"
    ),
    (
        "OpenAI / Provider API Key",
        re.compile(r"\b(?:sk-ant-|sk-proj-|sk-or-v1-|sk-admin-|gsk_)[a-zA-Z0-9_-]{20,}\b"),
        "[REDACTED_API_KEY]"
    ),
    (
        "Generic sk- API Key",
        re.compile(r"\bsk-[a-zA-Z0-9]{32,}\b"),
        "[REDACTED_API_KEY]"
    ),
    (
        "Google AI Key",
        re.compile(r"\b(?:AIza[0-9A-Za-z_-]{35}|AQ[0-9A-Za-z_.-]{25,})\b"),
        "[REDACTED_GOOGLE_KEY]"
    ),
    (
        "GitHub Token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[a-zA-Z0-9_]{36,}\b"),
        "[REDACTED_GITHUB_TOKEN]"
    ),
    (
        "Hugging Face Token",
        re.compile(r"\bhf_[a-zA-Z0-9]{34,}\b"),
        "[REDACTED_HF_TOKEN]"
    ),
    (
        "AWS Access Key ID",
        re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_ACCESS_KEY]"
    ),
    (
        "AWS Secret Access Key",
        re.compile(r"(?i)(aws_secret_access_key\s*[:=]\s*['\"]?)([A-Za-z0-9/+=]{40})(['\"]?)"),
        r"\g<1>[REDACTED_AWS_SECRET_KEY]\g<3>"
    ),
    (
        "Database Password",
        re.compile(r"(?i)\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^:\s]+:)([^@\s]+)(@)"),
        r"\g<1>[REDACTED_DB_PASSWORD]\g<3>"
    ),
    (
        "Generic Assigned Secret",
        re.compile(r"(?i)\b((?:api_key|apikey|secret_key|client_secret|auth_token|access_token|password|passwd|db_password)\s*[:=]\s*['\"])([^'\"\s]{8,})(['\"])"),
        r"\g<1>[REDACTED_SECRET]\g<3>"
    ),
]


def check_secret_leak(content: str) -> list[dict]:
    """
    Scan file content that is about to be written to disk for hardcoded
    secrets/API keys embedded by the AI in the source code.

    Unlike sanitize_outgoing_context (which redacts before sending to LLM),
    this function is the *outbound write guard*: it detects and reports
    findings so callers can warn the user, without blocking the write.

    Returns:
        List of dicts, each with keys:
          - "label"  (str): Human-readable credential type name.
          - "line"   (int): 1-indexed line number where the match was found.
          - "match"  (str): The matched secret token, partially redacted for display.
    """
    if not content:
        return []

    findings: list[dict] = []
    lines = content.splitlines()

    # Only scan the patterns that indicate a hardcoded literal credential.
    # We skip "Generic Assigned Secret" for now because it generates too many
    # false positives on placeholder strings like `api_key = "your-key-here"`.
    SCAN_LABELS = {
        "Private Key",
        "OpenAI / Provider API Key",
        "Generic sk- API Key",
        "Google AI Key",
        "GitHub Token",
        "Hugging Face Token",
        "AWS Access Key ID",
        "AWS Secret Access Key",
        "Database Password",
    }

    for label, pattern, _ in SECRET_PATTERNS:
        if label not in SCAN_LABELS:
            continue
        for lineno, line in enumerate(lines, start=1):
            m = pattern.search(line)
            if m:
                raw = m.group(0)
                # Partially redact for safe display: show first 6 and last 4 chars
                if len(raw) > 12:
                    display = raw[:6] + "..." + raw[-4:]
                else:
                    display = raw[:4] + "..."
                findings.append({"label": label, "line": lineno, "match": display})

    return findings


def sanitize_outgoing_context(text: str) -> tuple[str, list[str]]:
    """
    Scans outgoing prompt/file context for sensitive credentials, API keys,
    private keys, and passwords. Replaces them with a safe redacted placeholder.
    Returns:
        sanitized_text (str): The scrubbed content.
        detected_types (list[str]): List of credential types detected and sanitized.
    """
    if not text:
        return text, []

    detected_types = []
    sanitized = text

    for label, pattern, replacement in SECRET_PATTERNS:
        if pattern.search(sanitized):
            if label not in detected_types:
                detected_types.append(label)
            sanitized = pattern.sub(replacement, sanitized)

    return sanitized, detected_types

