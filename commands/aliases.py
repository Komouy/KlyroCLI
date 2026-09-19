"""
commands/aliases.py — Slash command shorthand aliases and fuzzy matching suggestions
"""

from typing import Optional

COMMON_SLASH_ALIASES = {
    "/q": "/quit",
    "/h": "/help",
    "/cls": "/clear",
    "/p": "/provider",
    "/m": "/cmodel",
    "/models": "/cmodel",
    "/u": "/undo",
    "/stat": "/usage",
    "/stats": "/usage",
    "/doc": "/doctor",
}

ALL_KNOWN_COMMANDS = [
    "/help", "/doctor", "/provider", "/setup", "/cmodel", "/model",
    "/registry", "/consensus", "/clear", "/usage", "/history",
    "/files", "/tree", "/find", "/symbols", "/diff", "/commit",
    "/run", "/undo", "/todo", "/cd", "/exit", "/quit"
]


def suggest_slash_command(cmd: str) -> Optional[str]:
    """Find closest matching slash command using difflib fuzzy matching."""
    import difflib
    cmd = cmd.strip().lower()
    matches = difflib.get_close_matches(cmd, ALL_KNOWN_COMMANDS, n=1, cutoff=0.5)
    return matches[0] if matches else None
