"""
approval_gate.py — Permission Manager / Approval Gate for CoreAgent (Priority 3)

Builds the `approval_callback` that core/agent.py's Agent calls before
executing ANY mutating tool (file_write, file_delete, mkdir, rename, shell —
see core/tool_registry.is_mutating_tool). Read-only tools (file_read,
file_search, symbol_search) never reach this module.

Deliberately kept OUTSIDE core/: core/agent.py and core/tool_registry.py
must stay usable headless (no terminal attached — see tests/demo_agent.py),
so they only know about an abstract Callable[[Action], bool]. This file is
the concrete CLI implementation of that callable, and it intentionally
reuses — rather than reimplements — the exact prompts and diff card the
legacy ACTION-tag pipeline already uses, so switching klyro_cli.py from
apply_actions.py/execute_ai_actions() to CoreAgent does not regress the
confirmation UX a user already relies on:

  - file_write  -> apply_actions.render_diff() (same diff card)
  - file_delete -> same "AI wants to DELETE" prompt as execute_ai_actions()
  - mkdir       -> same "AI wants to create directory" prompt
  - rename      -> same "AI wants to rename" prompt (+ overwrite warning)
  - shell       -> same security.check_command_safety() escalation as
                    execute_ai_actions() (default-deny on a dangerous-pattern
                    match, default-allow otherwise, but ALWAYS asks)

NOTE on batching: execute_ai_actions() shows one prompt for a comma-separated
multi-path <!--ACTION:DELETE path="a,b,c" --> tag. response_planner.py plans
that as three separate Actions (one per path), so this gate asks once per
path instead of once per tag. Same safety guarantee (nothing is deleted
without an explicit yes), just N prompts instead of 1 for a batched delete —
worth revisiting in core/response_planner.py later if that gets noisy.
"""

import os
from typing import Callable, Optional

from core.agent import Action
from theme import RESET, BOLD, FROST_CYAN, FROST_MINT, FROST_CORAL, FROST_WHITE, FROST_DARK
import security
import file_manager
import apply_actions


def build_approval_summary(action: Action, base_folder: str) -> str:
    """Return a single human-readable sentence explaining the pending action."""
    if not action or not action.tool_name:
        return "This action is not fully described yet."

    tool_name = action.tool_name
    args = action.args or {}

    if tool_name == "file_write":
        target = str(args.get("path", "<unknown path>"))
        content = str(args.get("content", ""))
        line_count = max(1, len(content.splitlines()))
        return f"Write {target} ({line_count} line(s))"

    if tool_name == "file_delete":
        target = str(args.get("path", "<unknown path>"))
        return f"Delete {target}"

    if tool_name == "mkdir":
        target = str(args.get("path", "<unknown path>"))
        return f"Create directory {target}"

    if tool_name == "rename":
        src = str(args.get("src", "<unknown source>"))
        dst = str(args.get("dst", "<unknown target>"))
        return f"Rename {src} -> {dst}"

    if tool_name == "shell":
        command = str(args.get("command", "<empty command>"))
        return f"Shell: {command}"

    return f"Perform {tool_name} action"


def _ask(prompt_text: str, default_deny: bool) -> bool:
    """Same yes/no semantics as every input()-based confirm in klyro_cli.py:
    default_deny=True means Ctrl-C/EOF/empty -> deny; default_deny=False
    means empty -> allow (so pressing Enter accepts the common case)."""
    try:
        allow = input(prompt_text).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        allow = "no" if default_deny else ""
    return (allow in ["yes", "y"]) if default_deny else (allow in ["", "y", "yes"])


def _confirm_file_write(action: Action, base_folder: str) -> bool:
    path_rel = (action.args or {}).get("path", "")
    content = (action.args or {}).get("content", "")
    target = os.path.join(base_folder, path_rel)

    if not file_manager.is_safe_path(base_folder, target, rel_path=path_rel):
        print(f"  {FROST_CORAL}✗{RESET} Akses ditolak (di luar workspace): {path_rel}")
        return False

    is_prot, prot_msg = file_manager.is_protected_workspace_path(path_rel)
    if is_prot:
        print(f"  {FROST_CORAL}✗{RESET} {prot_msg}")
        return False

    file_existed = os.path.exists(target)
    old_code, _ = file_manager.baca_satu_file(target) if file_existed else (None, None)
    summary = build_approval_summary(action, base_folder)
    print(f"\n  {FROST_CYAN}{BOLD}Review pending change:{RESET}")
    print(f"  {FROST_WHITE}{summary}{RESET}")
    print(f"  {FROST_DARK}Target: {path_rel}{RESET}")
    apply_actions.render_diff(old_code or "", content, path_rel)

    # Pre-write syntax / structural check
    ok_syntax, syntax_msg = file_manager.validasi_sintaks(path_rel, content, old_content=old_code)
    if not ok_syntax:
        print(f"  {FROST_AMBER}⚠️  Syntax/Structural Warning:{RESET} {FROST_CORAL}{syntax_msg}{RESET}")
        return _ask(
            f"  {FROST_CORAL}File contains syntax errors. Apply to {BOLD}{path_rel}{RESET} anyway? (yes/N): ",
            default_deny=True,
        )

    return _ask(
        f"  {FROST_CYAN}Apply this change? {FROST_DARK}[Y/n]{RESET} ",
        default_deny=False,
    )


def _confirm_file_delete(action: Action, base_folder: str) -> bool:
    path_rel = (action.args or {}).get("path", "")
    target = os.path.join(base_folder, path_rel)

    if not file_manager.is_safe_path(base_folder, target, rel_path=path_rel):
        print(f"  {FROST_CORAL}✗{RESET} Akses ditolak: {path_rel}")
        return False

    is_prot, prot_msg = file_manager.is_protected_workspace_path(path_rel)
    if is_prot:
        print(f"  {FROST_CORAL}✗{RESET} {prot_msg}")
        return False

    if not os.path.exists(target):
        print(f"  {FROST_DARK}⊘ File/folder not found: {path_rel}{RESET}")
        return False

    kind = "folder" if os.path.isdir(target) else "file"
    summary = build_approval_summary(action, base_folder)
    print(f"\n  {FROST_CORAL}{BOLD}⚠️  Destructive action requested:{RESET}")
    print(f"  {FROST_WHITE}{summary}{RESET}")
    print(f"  {FROST_DARK}Target: {path_rel} ({kind}){RESET}")

    return _ask(f"  {FROST_CORAL}Confirm deletion? (yes/N):{RESET} ", default_deny=True)


def _confirm_mkdir(action: Action, base_folder: str) -> bool:
    path_rel = (action.args or {}).get("path", "")
    target = os.path.join(base_folder, path_rel)

    if not file_manager.is_safe_path(base_folder, target, rel_path=path_rel):
        print(f"  {FROST_CORAL}✗{RESET} Akses ditolak (path traversal): {path_rel}")
        return False

    summary = build_approval_summary(action, base_folder)
    print(f"\n  {FROST_CYAN}{BOLD}Folder creation request:{RESET}")
    print(f"  {FROST_WHITE}{summary}{RESET}")
    print(f"  {FROST_DARK}Target: {path_rel}{RESET}")
    return _ask(f"  {FROST_CYAN}Create this directory? (Y/n):{RESET} ", default_deny=False)


def _confirm_rename(action: Action, base_folder: str) -> bool:
    src_rel = (action.args or {}).get("src", "")
    dst_rel = (action.args or {}).get("dst", "")
    src = os.path.join(base_folder, src_rel)
    dst = os.path.join(base_folder, dst_rel)

    if not file_manager.is_safe_path(base_folder, src, rel_path=src_rel) or not file_manager.is_safe_path(
        base_folder, dst, rel_path=dst_rel
    ):
        print(f"  {FROST_CORAL}✗{RESET} Akses ditolak (path traversal): {src_rel} → {dst_rel}")
        return False

    is_prot, prot_msg = file_manager.is_protected_workspace_path(src_rel)
    if not is_prot:
        is_prot, prot_msg = file_manager.is_protected_workspace_path(dst_rel)
    if is_prot:
        print(f"  {FROST_CORAL}✗{RESET} {prot_msg}")
        return False

    if not os.path.exists(src):
        print(f"  {FROST_CORAL}✗{RESET} Source not found: {src_rel}")
        return False

    overwrite_warning = ""
    if os.path.exists(dst):
        overwrite_warning = f"  {FROST_CORAL}(will overwrite existing {dst_rel}){RESET}"

    summary = build_approval_summary(action, base_folder)
    print(f"\n  {FROST_CYAN}{BOLD}Rename request:{RESET}")
    print(f"  {FROST_WHITE}{summary}{RESET}")
    print(f"  {FROST_DARK}From: {src_rel}{RESET}")
    print(f"  {FROST_DARK}To:   {dst_rel}{RESET}{overwrite_warning}")
    return _ask(f"  {FROST_CYAN}Confirm rename? (Y/n):{RESET} ", default_deny=False)


def _confirm_shell(action: Action, base_folder: str) -> bool:
    cmd = (action.args or {}).get("command", "")
    if not cmd:
        return False

    is_interactive, interactive_reason = security.check_interactive_command(cmd)
    if is_interactive:
        print(f"\n  {FROST_CORAL}{BOLD}⚠️  BLOCKED — INTERACTIVE COMMAND:{RESET}")
        print(f"  {FROST_DARK}Command : {cmd}{RESET}")
        print(f"  {FROST_CORAL}Reason  : {interactive_reason}{RESET}")
        print(f"  {FROST_DARK}Interactive commands hang automated agent execution. Denied.{RESET}\n")
        return False

    is_danger, risk = security.check_command_safety(cmd)
    summary = build_approval_summary(action, base_folder)

    # Every AI-issued shell command requires confirmation, always - a
    # denylist miss is NOT treated as "safe" (see security.py's design
    # note). A denylist HIT just escalates the prompt to a louder,
    # default-deny warning.
    if is_danger:
        print(f"\n  {FROST_CORAL}{BOLD}⚠️  SAFETY WARNING — DANGEROUS AI ACTION:{RESET}")
        print(f"  {FROST_WHITE}{summary}{RESET}")
        print(f"  {FROST_DARK}Command: {cmd}{RESET}")
        print(f"  {FROST_DARK}Risk   : {risk}{RESET}")
        return _ask(f"  {FROST_CORAL}Allow execution? (yes/N):{RESET} ", default_deny=True)

    print(f"\n  {FROST_CYAN}{BOLD}Command approval request:{RESET}")
    print(f"  {FROST_WHITE}{summary}{RESET}")
    print(f"  {FROST_DARK}Command: {cmd}{RESET}")
    return _ask(f"  {FROST_CYAN}Allow execution? (Y/n):{RESET} ", default_deny=False)


# One confirmer per mutating tool name (core/tool_registry.MUTATING_TOOL_NAMES).
# Keep this dict's keys in sync with that set — make_approval_gate() below
# fails closed (denies) for any mutating tool name that shows up here without
# a matching confirmer, instead of silently letting it through unreviewed.
_CONFIRMERS = {
    "file_write": _confirm_file_write,
    "file_delete": _confirm_file_delete,
    "mkdir": _confirm_mkdir,
    "rename": _confirm_rename,
    "shell": _confirm_shell,
}


def make_approval_gate(base_folder: str) -> Callable[[Action], bool]:
    """
    Build the `approval_callback` to pass into `Agent(approval_callback=...)`.

    Agent already only calls this for mutating tool calls (via
    tool_registry.is_mutating_tool), so every Action reaching `gate()` here
    is expected to be one of the tools in _CONFIRMERS.
    """

    def gate(action: Action) -> bool:
        confirmer = _CONFIRMERS.get(action.tool_name)
        if confirmer is None:
            # A mutating tool got registered/planned without a matching
            # confirmer being added here - fail closed rather than
            # silently allow an unreviewed mutation type through.
            print(
                f"\n  {FROST_CORAL}⚠️  No confirmation prompt wired for tool "
                f"'{action.tool_name}' — denying by default.{RESET}"
            )
            return False
        return confirmer(action, base_folder)

    return gate
