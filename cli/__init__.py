"""
cli package — Terminal user interface, animations, menu selection and autocompletion
"""

from cli.spinner import (
    Spinner,
    CancellationMonitor,
    prompt_secret,
    static_box_width,
    print_banner,
    play_startup_animation,
)
from cli.interactive_menu import interactive_select
from cli.completer import (
    KlyroCompleter,
    SLASH_COMMANDS,
    _frost_style,
)

__all__ = [
    "Spinner",
    "CancellationMonitor",
    "prompt_secret",
    "static_box_width",
    "print_banner",
    "play_startup_animation",
    "interactive_select",
    "KlyroCompleter",
    "SLASH_COMMANDS",
    "_frost_style",
]
