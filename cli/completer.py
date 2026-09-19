"""
cli/completer.py — Autocomplete completer for slash commands and workspace file mentions
"""

import os
import file_manager

try:
    from prompt_toolkit.completion import Completer, Completion, PathCompleter
    from prompt_toolkit.styles import Style
    from prompt_toolkit.formatted_text import HTML
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False
    Completer = object
    Completion = None
    PathCompleter = None
    Style = None
    HTML = None


SLASH_COMMANDS = [
    ("/help",     "Show all available commands"),
    ("/doctor",   "Run system, API & network diagnostics"),
    ("/provider", "Setup AI provider & API key"),
    ("/cmodel",   "List or switch active model"),
    ("/model",    "Alias for /cmodel (switch active model)"),
    ("/registry", "View or refresh OpenRouter Model Registry"),
    ("/commit",   "Auto-generate AI commit message & commit"),
    ("/consensus","Toggle multi-model consensus mode"),
    ("/router",   "Smart workload-based routing & auto-fallback"),
    ("/think",    "Visual thought process & deep reasoning stream"),
    ("/undo",     "Revert last AI file modifications"),
    ("/todo",     "Scan workspace for TODO & FIXME comments"),
    ("/usage",    "View tokens, latency & cost tracker"),
    ("/history",  "View or clear session history"),
    ("/files",    "List all project files with sizes"),
    ("/tree",     "Display folder tree visualizer"),
    ("/find",     "Find files by glob pattern"),
    ("/symbols",  "Find functions/classes by name across project"),
    ("/run",      "Run project or shell command"),
    ("/diff",     "Show git status and diff"),
    ("/clear",    "Clear terminal & reset conversation"),
    ("/cd",       "Change active project directory"),
    ("/exit",     "Exit Klyro Code"),
    ("/quit",     "Exit Klyro Code"),
    ("/q",        "Alias for /quit"),
    ("/h",        "Alias for /help"),
    ("/cls",      "Alias for /clear"),
    ("/p",        "Alias for /provider"),
    ("/m",        "Alias for /cmodel"),
    ("/u",        "Alias for /undo"),
    ("/stat",     "Alias for /usage"),
]

if PROMPT_TOOLKIT_AVAILABLE:
    _frost_style = Style.from_dict({
        "completion-menu":              "bg:#1e2433 #bae6fd",
        "completion-menu.completion":   "bg:#1e2433 #bae6fd",
        "completion-menu.completion.current": "bg:#0f172a #38bdf8 bold",
        "scrollbar.background":         "bg:#1e2433",
        "scrollbar.button":             "bg:#334155",
    })

    class KlyroCompleter(Completer):
        def __init__(self, get_folder_aktif=None):
            self._path_completer = PathCompleter(only_directories=True, expanduser=True)
            self._get_folder_aktif = get_folder_aktif

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor

            # ── /cd <path> → filesystem folder autocomplete ───────────
            if text.lower().startswith("/cd "):
                path_part = text[4:]  # strip "/cd "
                from prompt_toolkit.document import Document as PTDocument
                path_doc = PTDocument(path_part, cursor_position=len(path_part))
                for c in self._path_completer.get_completions(path_doc, complete_event):
                    yield c
                return

            # ── /cmodel or /model subcommands ────────────────────────
            lowered = text.lower()
            if lowered.startswith(("/cmodel ", "/model ", "/m ")):
                prefix = lowered.split(maxsplit=1)[1] if " " in lowered else ""
                subcmds = [
                    ("refresh", "Fetch live model list from provider API"),
                    ("restart", "Fetch live model list (alias)"),
                    ("sync",    "Fetch live model list (alias)"),
                    ("reload",  "Fetch live model list (alias)"),
                    ("update",  "Fetch live model list (alias)"),
                ]
                for sc, desc in subcmds:
                    if sc.startswith(prefix):
                        display = HTML(f"<b>{sc}</b>  <ansigray>{desc}</ansigray>")
                        yield Completion(
                            sc,
                            start_position=-len(prefix),
                            display=display,
                        )
                return

            # ── @filename → workspace file autocomplete ───────────────
            at_idx = text.rfind("@")
            if at_idx != -1:
                if at_idx == 0 or text[at_idx - 1] in " \t([{":
                    prefix = text[at_idx + 1:].lower().replace("\\", "/")
                    folder = self._get_folder_aktif() if self._get_folder_aktif else None
                    if folder and os.path.isdir(folder):
                        file_candidates = file_manager.list_daftar_file(folder)
                        for f in file_candidates:
                            f_norm = f.replace("\\", "/")
                            f_base = os.path.basename(f_norm)
                            if f_norm.lower().startswith(prefix) or f_base.lower().startswith(prefix):
                                safe_file = f_norm.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                                display = HTML(f"<b>@{safe_file}</b> <ansigray>(file)</ansigray>")
                                yield Completion(
                                    "@" + f_norm,
                                    start_position=-(len(text) - at_idx),
                                    display=display,
                                )
                        return

            # ── / → slash command suggestions ─────────────────────────
            if not text.startswith("/"):
                return
            word = text.lower()
            for cmd, desc in SLASH_COMMANDS:
                if cmd.startswith(word):
                    safe_desc = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    display = HTML(f"<b>{cmd}</b>  <ansigray>{safe_desc}</ansigray>")
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=display,
                    )
else:
    _frost_style = None
    class KlyroCompleter:
        def __init__(self, get_folder_aktif=None):
            pass
