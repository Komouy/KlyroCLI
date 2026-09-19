"""Apply named markdown fences to disk, with a display-width-aware diff card."""

import os
import re
import shutil


import file_manager
import undo_manager
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_MINT, FROST_CORAL, FROST_WHITE, FROST_DARK,
    FROST_INDIGO, FROST_GHOST, FROST_AMBER,
    wrap_by_display_width,
    UI,
)


# Patterns for ACTION tag validation
_ACTION_FULL_TAG_RE = re.compile(r'<!--\s*ACTION:(\w+)\s+(.*?)\s*-->', re.IGNORECASE | re.DOTALL)
_ACTION_ATTR_RE     = re.compile(r'(\w+)="([^"]*?)"')
_ACTION_START_RE    = re.compile(r'<!--\s*ACTION:', re.IGNORECASE)


def validate_ai_response_integrity(response_text: str) -> list[str]:
    """
    Validate AI response integrity before parsing and applying actions:
    1. Detects unclosed markdown code fences (indicates truncated generation).
    2. Detects named code blocks with empty or whitespace-only content.
    3. Validates ACTION comment tags:
       - Checks for unclosed action tags (e.g. <!--ACTION:SHELL cmd=... without -->).
       - Validates known action types (DELETE, RENAME, MKDIR, SHELL).
       - Verifies required attributes for each action type.
    Returns a list of warning descriptions.
    """
    warnings = []
    if not response_text:
        return warnings

    # 1. Unclosed code fences check
    lines = response_text.splitlines()
    fence_stack = []
    for line in lines:
        stripped = line.strip()
        m = re.match(r"^(`{3,}|~{3,})", stripped)
        if m:
            ticks = m.group(1)
            char = ticks[0]
            length = len(ticks)
            rest = stripped[length:].strip()
            if not fence_stack:
                fence_stack.append((char, length, rest))
            else:
                top_char, top_len, _ = fence_stack[-1]
                # If bare closing fence with same char and at least same length
                if char == top_char and length >= top_len and not rest:
                    fence_stack.pop()
                elif char == top_char and rest and (":" in rest or "." in rest):
                    # New named fence opened while previous unclosed
                    fence_stack.append((char, length, rest))

    if fence_stack:
        warnings.append(
            "Unclosed code fence detected (AI response may have been truncated mid-generation)."
        )

    # 2. Empty file writes check
    try:
        fences = file_manager.extract_named_file_fences(response_text)
        for fname, content in fences.items():
            if not content.strip():
                warnings.append(f"Named file write for '{fname}' has empty content.")
    except Exception:
        pass

    # 3. ACTION tags check
    total_starts = len(_ACTION_START_RE.findall(response_text))
    matched_tags = list(_ACTION_FULL_TAG_RE.finditer(response_text))
    if total_starts > len(matched_tags):
        warnings.append(
            f"Detected {total_starts - len(matched_tags)} unclosed or malformed ACTION tag(s)."
        )

    KNOWN_ACTIONS = {"DELETE", "RENAME", "MKDIR", "SHELL"}
    for match in matched_tags:
        action_type = match.group(1).upper()
        attrs_raw   = match.group(2)
        attrs       = dict(_ACTION_ATTR_RE.findall(attrs_raw))

        if action_type not in KNOWN_ACTIONS:
            warnings.append(f"Unknown ACTION type '{action_type}' (expected DELETE, RENAME, MKDIR, or SHELL).")
            continue

        if action_type == "DELETE":
            path_val = attrs.get("path", "").strip()
            if not path_val:
                warnings.append("ACTION:DELETE is missing required 'path' attribute.")
        elif action_type == "RENAME":
            src = attrs.get("from", "").strip()
            dst = attrs.get("to", "").strip()
            if not src or not dst:
                warnings.append("ACTION:RENAME requires both 'from' and 'to' attributes.")
        elif action_type == "MKDIR":
            path_val = attrs.get("path", "").strip()
            if not path_val:
                warnings.append("ACTION:MKDIR is missing required 'path' attribute.")
        elif action_type == "SHELL":
            cmd = attrs.get("cmd", "").strip()
            if not cmd:
                warnings.append("ACTION:SHELL is missing required 'cmd' attribute.")

    return warnings


def render_diff(old_text, new_text, filename):
    """Render unified color diff in Nordic Frost rounded card with stats banner."""
    import difflib
    old_lines = (old_text or "").splitlines(keepends=True)
    new_lines = (new_text or "").splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=3
    ))

    if not diff:
        print(f"  {FROST_DARK}(No changes detected){RESET}")
        return

    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    box_width = max(40, term_width - 6)

    adds = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    stat_badge = f"{FROST_MINT}+{adds}{RESET} {FROST_CORAL}-{dels}{RESET}"

    UI.card_start(f"Proposed changes for {BOLD}{FROST_WHITE}{filename}{RESET}", stat_badge, box_width=box_width)

    for line in diff:
        line_clean = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            UI.card_line(line_clean, " ", f"{BOLD}{FROST_GHOST}", box_width=box_width)
        elif line.startswith("@@"):
            UI.card_line(line_clean, " ", FROST_INDIGO, box_width=box_width)
        elif line.startswith("+"):
            UI.card_line(line_clean[1:], "+", FROST_MINT, box_width=box_width)
        elif line.startswith("-"):
            UI.card_line(line_clean[1:], "-", FROST_CORAL, box_width=box_width)
        else:
            body = line_clean[1:] if line.startswith(" ") else line_clean
            UI.card_line(body, " ", "", box_width=box_width)
    UI.card_end(box_width=box_width)


def parse_and_apply_actions(response_text, folder_aktif, ai_assistant):
    """Detect code blocks with filename and offer to apply to disk.
    Supported formats:
      1. ```lang:filename.ext  (explicit)
      2. ### FILE: filename.ext
      3. ```lang\\n# filename.ext  (comment hint on first line)
      4. ```lang\\n// filename.ext (comment hint on first line)
    """
    # Validate response integrity (unclosed fences, empty writes, malformed tags)
    integrity_warnings = validate_ai_response_integrity(response_text)
    for warn in integrity_warnings:
        UI.warning(f"Integrity alert: {warn}")

    seen_files = file_manager.extract_named_file_fences(response_text)
    applied_ops = []
    apply_all = False
    multi_files = len(seen_files) > 1

    for filename, new_code in seen_files.items():
        filename = filename.strip()
        target_path = os.path.join(folder_aktif, filename)
        if not file_manager.is_safe_path(folder_aktif, target_path, rel_path=filename):
            UI.error(f"Akses ditolak (di luar workspace): {filename}")
            continue

        is_prot, prot_msg = file_manager.is_protected_workspace_path(filename)
        if is_prot:
            UI.error(prot_msg)
            continue

        file_existed = os.path.exists(target_path)
        old_code, _ = file_manager.baca_satu_file(target_path) if file_existed else ("", None)
        body = new_code.strip()
        render_diff(old_code or "", body, filename)

        seen_fully = True
        if file_existed and ai_assistant is not None:
            try:
                seen_fully = ai_assistant.was_file_fully_seen(filename)
            except Exception:
                seen_fully = True

        # Pre-write syntax validation
        ok_syntax, syntax_msg = file_manager.validasi_sintaks(filename, body, old_content=old_code)
        if not ok_syntax:
            UI.syntax_warning(filename, syntax_msg)

        has_unclosed_fence = any("Unclosed code fence" in w for w in integrity_warnings)
        if has_unclosed_fence:
            UI.warning(f"File {BOLD}{filename}{RESET} is from an incomplete/truncated response.\n  Applying will write broken or cut-off code to disk. Review the diff above carefully.")
            prompt_str = f"  {FROST_CORAL}Apply truncated changes to {BOLD}{filename}{RESET} anyway? (yes/N):{RESET} "
            default_deny = True
        elif not ok_syntax:
            prompt_str = f"  {FROST_CORAL}File contains syntax/structural errors ({syntax_msg}). Apply to {BOLD}{filename}{RESET} anyway? (yes/N):{RESET} "
            default_deny = True
        elif not seen_fully:
            UI.warning(f"the AI's project context was truncated and it likely\n  never saw the real current content of {BOLD}{filename}{RESET} — this rewrite may be\n  based on a guess, not the actual file. Review the diff above carefully.")
            prompt_str = f"  {FROST_CORAL}Apply anyway? (yes/N):{RESET} "
            default_deny = True
        else:
            if multi_files:
                prompt_str = f"  {FROST_CYAN}Apply changes to {BOLD}{filename}{RESET}? {FROST_DARK}[Y/n/a (all)]{RESET} "
            else:
                prompt_str = f"  {FROST_CYAN}Apply changes to {BOLD}{filename}{RESET}? {FROST_DARK}[Y/n]{RESET} "
            default_deny = False

        if apply_all and not default_deny:
            allowed = True
        else:
            try:
                ans = input(prompt_str).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print(f"\n  {FROST_DARK}Skipped.{RESET}")
                continue

            if not default_deny and ans in ("a", "all"):
                apply_all = True
                allowed = True
            elif default_deny:
                allowed = ans in ("yes", "y")
            else:
                allowed = ans in ("", "y", "yes")

        if allowed:
            sukses, msg = file_manager.tulis_file(target_path, body, buat_backup=True)
            if sukses:
                UI.file_updated(filename)
                if not ok_syntax:
                    UI.syntax_warning(filename, f"Applied with syntax warning: {syntax_msg}")
                if file_existed:
                    applied_ops.append({"type": "modify", "path": target_path, "old_content": old_code or ""})
                else:
                    applied_ops.append({"type": "create", "path": target_path})
            else:
                UI.error(f"Failed: {msg}")
        else:
            print(f"  {FROST_DARK}Skipped.{RESET}")

    if applied_ops:
        undo_manager.record_transaction(folder_aktif, applied_ops)
        if ai_assistant is not None:
            konteks, file_dibaca, _ = file_manager.baca_semua_file(folder_aktif)
            ai_assistant.set_folder_context(
                folder_aktif,
                konteks,
                jumlah_file=len(file_dibaca),
                daftar_file=file_manager.list_daftar_file(folder_aktif),
            )
