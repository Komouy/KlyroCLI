"""
validations.py — Pre-flight safety checks & input guards for Klyro CLI.

Validation 3: Dirty Git Working Tree Guard
Validation 4: Empty Input & Accidental Enter Protection
Validation 5: Smart Ollama Pre-flight Ping
"""

from __future__ import annotations

import os
import re
import subprocess
import socket
import urllib.request
import urllib.error


# ─────────────────────────────────────────────────────────────
# V3: DIRTY GIT WORKING TREE GUARD
# ─────────────────────────────────────────────────────────────

def get_dirty_git_files(folder: str) -> list[str]:
    """Return list of uncommitted tracked files in the git repo at `folder`."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return []
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        dirty = [l[3:].strip() for l in lines if l[:2].strip() and l[:2] != "??"]
        return dirty
    except Exception:
        return []


WRITE_KEYWORDS = [
    "refactor", "rewrite", "edit", "modify", "update", "change",
    "rename", "delete", "remove", "add ", "create ", "implement",
    "fix ", "move ", "replace", "clean", "ubah", "buat", "tulis",
    "hapus", "pindah", "tambah", "ganti", "perbaiki",
]


def check_dirty_git_guard(folder: str, prompt: str) -> bool:
    """Warn if workspace has uncommitted changes and prompt looks write-heavy.

    Returns True  → safe to proceed.
    Returns False → user chose to abort.
    """
    prompt_lower = prompt.lower()
    if not any(kw in prompt_lower for kw in WRITE_KEYWORDS):
        return True

    dirty_files = get_dirty_git_files(folder)
    if not dirty_files:
        return True

    from theme import RESET, BOLD, FROST_AMBER, FROST_CORAL, FROST_DARK, FROST_CYAN, FROST_WHITE
    print(f"\n  {FROST_AMBER}{BOLD}⚠️  Dirty Git Working Tree Detected{RESET}")
    print(f"  {FROST_DARK}The following files have uncommitted changes:{RESET}")
    for f in dirty_files[:10]:
        print(f"  {FROST_WHITE}  • {f}{RESET}")
    if len(dirty_files) > 10:
        print(f"  {FROST_DARK}  … and {len(dirty_files) - 10} more{RESET}")
    print(f"  {FROST_DARK}Tip: run {FROST_CYAN}/commit{FROST_DARK} or {FROST_CYAN}!git stash{FROST_DARK} first to protect your work.{RESET}")

    try:
        ans = input(f"  {FROST_CORAL}Proceed anyway? (y/N):{RESET} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        ans = "n"
        print()

    return ans in ("y", "yes")


# ─────────────────────────────────────────────────────────────
# V4: EMPTY INPUT & ACCIDENTAL ENTER PROTECTION
# ─────────────────────────────────────────────────────────────

_consecutive_empty = 0
_EMPTY_HINT_THRESHOLD = 3


def check_empty_input(raw_input: str) -> bool:
    """Return True if input should be skipped (blank or punctuation noise)."""
    global _consecutive_empty

    stripped = raw_input.strip()
    if not stripped or re.fullmatch(r'[.,;:!?\-_\s]+', stripped):
        _consecutive_empty += 1
        if _consecutive_empty >= _EMPTY_HINT_THRESHOLD:
            from theme import RESET, FROST_DARK, FROST_CYAN
            print(f"  {FROST_DARK}Tip: type {FROST_CYAN}/help{FROST_DARK} for commands or {FROST_CYAN}/exit{FROST_DARK} to quit.{RESET}")
            _consecutive_empty = 0
        return True

    _consecutive_empty = 0
    return False


# ─────────────────────────────────────────────────────────────
# V5: SMART OLLAMA PRE-FLIGHT PING
# ─────────────────────────────────────────────────────────────

_ollama_probe_cache: dict = {}


def ping_ollama(base_url: str = "http://localhost:11434/v1", timeout: float = 1.5) -> tuple:
    """Quick HTTP probe to check if the Ollama/custom endpoint is alive."""
    global _ollama_probe_cache
    if base_url in _ollama_probe_cache:
        return _ollama_probe_cache[base_url]

    url = base_url.strip().rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KlyroCLI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = (True, f"Endpoint active (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        result = (True, f"Endpoint reachable (HTTP {e.code})")
    except (urllib.error.URLError, OSError, socket.timeout):
        result = (False, f"Cannot reach {base_url} — is 'ollama serve' running?")
    except Exception as e:
        result = (False, f"Probe failed: {e}")

    _ollama_probe_cache[base_url] = result
    return result


def check_ollama_preflight(ai_assistant) -> bool:
    """Probe the Ollama endpoint if the active provider is 'custom'.

    Returns True  → safe to proceed.
    Returns False → endpoint unreachable.
    """
    if not ai_assistant:
        return True

    provider = getattr(ai_assistant, "provider", "")
    if provider != "custom":
        return True

    base_url = "http://localhost:11434/v1"
    try:
        cfg = ai_assistant.config if hasattr(ai_assistant, "config") else {}
        base_url = cfg.get("custom_base_url", base_url)
    except Exception:
        pass

    ok, msg = ping_ollama(base_url)
    if ok:
        return True

    from theme import RESET, BOLD, FROST_CORAL, FROST_AMBER, FROST_DARK, FROST_CYAN
    print(f"\n  {FROST_CORAL}{BOLD}⚡ Ollama Pre-flight Check Failed{RESET}")
    print(f"  {FROST_DARK}{msg}{RESET}")
    print(f"  {FROST_AMBER}Fix: run {FROST_CYAN}ollama serve{FROST_AMBER} in another terminal, then retry.{RESET}")
    print(f"  {FROST_DARK}Or switch provider with {FROST_CYAN}/provider{FROST_DARK}.{RESET}\n")

    _ollama_probe_cache.pop(base_url, None)
    return False


def reset_ollama_cache(base_url: str = None) -> None:
    """Clear the Ollama probe cache."""
    global _ollama_probe_cache
    if base_url:
        _ollama_probe_cache.pop(base_url, None)
    else:
        _ollama_probe_cache.clear()


# ─────────────────────────────────────────────────────────────
# V6: LARGE FILE & LOCKFILE MENTION GUARD
# ─────────────────────────────────────────────────────────────

BLOCKED_LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "pipfile.lock",
    "packages.lock.json",
}

BLOCKED_MINIFIED_EXTENSIONS = {
    ".min.js",
    ".min.css",
    ".map",
    ".bundle.js",
}

MAX_FILE_MENTION_SIZE_BYTES = 200 * 1024  # 200 KB limit for single file in @mention context


def validate_file_mention_candidate(file_rel: str, abs_path: str = None) -> tuple[bool, str]:
    """
    Validates if a file mentioned with @filename is suitable for inclusion
    in LLM prompt context. Blocks lockfiles, minified bundles, and oversized files.
    Returns:
        (is_allowed: bool, reason: str)
    """
    if not file_rel:
        return False, "Empty file path"

    basename = os.path.basename(file_rel).lower()
    if basename in BLOCKED_LOCKFILES:
        return False, f"Lockfile '{basename}' is auto-generated metadata and excluded to save context"

    file_rel_lower = file_rel.lower()
    for min_ext in BLOCKED_MINIFIED_EXTENSIONS:
        if file_rel_lower.endswith(min_ext):
            return False, f"Minified file '{basename}' is excluded to save context"

    if abs_path and os.path.isfile(abs_path):
        try:
            sz = os.path.getsize(abs_path)
            if sz > MAX_FILE_MENTION_SIZE_BYTES:
                sz_kb = round(sz / 1024.0, 1)
                return False, f"File size ({sz_kb} KB) exceeds 200 KB context limit"
        except OSError:
            pass

    return True, ""


# ─────────────────────────────────────────────────────────────
# V7: POST-EDIT SYNTAX / LINTER VALIDATION
# ─────────────────────────────────────────────────────────────

def run_post_edit_diagnostics(file_path: str, content: str = None) -> tuple[bool, str, dict]:
    """
    Validates syntax and linter status of a newly edited/written file.
    Runs fast AST checks, compile tests, format parses (JSON/TOML), and balanced delimiter checks.
    Returns:
        is_clean (bool): True if no errors detected.
        summary_msg (str): Short summary for human/agent consumption.
        details (dict): Structured diagnostic details (lineno, error, snippet, etc.)
    """
    if content is None and os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return False, f"Failed to read file for diagnostics: {e}", {"error": str(e)}

    if content is None:
        return True, "No content to validate", {}

    details = {"file": file_path, "errors": []}
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == ".py":
        import ast
        try:
            ast.parse(content, filename=os.path.basename(file_path))
        except SyntaxError as e:
            line_no = e.lineno or 1
            col_offset = e.offset or 0
            snippet = e.text.strip() if e.text else ""
            err_dict = {
                "type": "SyntaxError",
                "line": line_no,
                "column": col_offset,
                "message": e.msg,
                "snippet": snippet
            }
            details["errors"].append(err_dict)
            summary = f"SyntaxError on line {line_no}: {e.msg}"
            if snippet:
                summary += f" (`{snippet}`)"
            return False, summary, details

        # Try compile probe in memory
        try:
            compile(content, file_path, "exec")
        except SyntaxError as e:
            line_no = e.lineno or 1
            err_dict = {
                "type": "CompileError",
                "line": line_no,
                "message": e.msg,
            }
            details["errors"].append(err_dict)
            return False, f"CompileError on line {line_no}: {e.msg}", details
        except Exception:
            pass

        return True, "Python syntax clean", details

    elif ext == ".json":
        import json
        try:
            json.loads(content)
            return True, "JSON format valid", details
        except json.JSONDecodeError as e:
            err_dict = {
                "type": "JSONDecodeError",
                "line": e.lineno,
                "column": e.colno,
                "message": e.msg
            }
            details["errors"].append(err_dict)
            return False, f"JSONDecodeError on line {e.lineno}, col {e.colno}: {e.msg}", details

    elif ext == ".toml":
        try:
            import tomllib
            tomllib.loads(content)
            return True, "TOML format valid", details
        except Exception as e:
            err_dict = {"type": "TOMLDecodeError", "message": str(e)}
            details["errors"].append(err_dict)
            return False, f"TOML Decode Error: {e}", details

    elif ext in [".js", ".jsx", ".ts", ".tsx", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java", ".cs", ".php"]:
        try:
            import file_manager
            ok, msg = file_manager.check_balanced_delimiters(content)
            if not ok:
                err_dict = {"type": "DelimiterMismatch", "message": msg}
                details["errors"].append(err_dict)
                return False, msg, details
        except Exception:
            pass
        return True, "Delimiter balance valid", details

    return True, "No specific validator for this file type", details


