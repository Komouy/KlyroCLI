"""
commands package — Slash command dispatcher, provider wizard, and AI action executor
"""

from commands.command_handler import handle_slash_command, execute_ai_actions, run_auto_commit
from commands.provider_wizard import run_provider_wizard
from commands.aliases import COMMON_SLASH_ALIASES, ALL_KNOWN_COMMANDS, suggest_slash_command

__all__ = [
    "handle_slash_command",
    "execute_ai_actions",
    "run_auto_commit",
    "run_provider_wizard",
    "COMMON_SLASH_ALIASES",
    "ALL_KNOWN_COMMANDS",
    "suggest_slash_command",
]
