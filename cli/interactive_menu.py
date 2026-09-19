"""
cli/interactive_menu.py — Arrow-key navigable card menu for model & option selection
"""

import sys
import time

from cli.spinner import static_box_width
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_ICE, FROST_MINT,
    FROST_WHITE, FROST_DARK, FROST_GHOST,
    keycap,
)


def interactive_select(title: str, options: list[dict], default_idx: int = 0) -> int:
    """
    Renders an interactive selection menu using ArrowUp/ArrowDown in a sleek rounded card.
    Each option in options list should be: {"label": str, "description": str}
    Returns: chosen index (0-based) or -1 if cancelled (Esc).
    """
    current_idx = default_idx
    num_options = len(options)
    if num_options == 0:
        return -1

    # Hide cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    card_width = static_box_width(68)

    def print_menu():
        # Title — sleek glowing header
        sys.stdout.write(f"\n  {FROST_DARK}╭─ {FROST_CYAN}{BOLD}{title}{RESET} {FROST_DARK}{'─'*(card_width - len(title) - 5)}╮{RESET}\n")
        for idx, opt in enumerate(options):
            is_selected = (idx == current_idx)
            if is_selected:
                arrow  = f"{FROST_CYAN}❯{RESET}"
                label  = f"{BOLD}{FROST_WHITE}{opt['label']:<24}{RESET}"
                desc   = opt.get("description", "")
                desc_c = f"{FROST_ICE}{desc}{RESET}"
                sys.stdout.write(f"  {FROST_DARK}│{RESET}  {arrow} {label} {desc_c}\n")
            else:
                arrow  = " "
                label  = f"{FROST_GHOST}{opt['label']:<24}{RESET}"
                desc   = opt.get("description", "")
                desc_c = f"{FROST_DARK}{desc}{RESET}"
                sys.stdout.write(f"  {FROST_DARK}│{RESET}  {arrow} {label} {desc_c}\n")
        # Bottom border & navigation hints
        sys.stdout.write(f"  {FROST_DARK}╰{'─'*card_width}╯{RESET}\n")
        nav_hint = f"  {keycap('↑/↓')} {FROST_DARK}Navigate{RESET}  {keycap('Enter')} {FROST_DARK}Select{RESET}  {keycap('Esc')} {FROST_DARK}Cancel{RESET}\n"
        sys.stdout.write(nav_hint)
        sys.stdout.flush()

    def clear_menu():
        # lines: 1 blank + 1 top-border + N options + 1 bottom-border + 1 hint
        lines_to_clear = num_options + 4
        for _ in range(lines_to_clear):
            sys.stdout.write("\033[F\033[K")
        sys.stdout.flush()

    try:
        print_menu()
        while True:
            key = None
            try:
                if sys.platform == "win32":
                    import msvcrt
                    while not msvcrt.kbhit():
                        time.sleep(0.01)
                    ch = msvcrt.getch()
                    if ch in (b'\x00', b'\xe0'):
                        ch2 = msvcrt.getch()
                        if ch2 == b'H': key = 'up'
                        elif ch2 == b'P': key = 'down'
                    elif ch == b'\r':
                        key = 'enter'
                    elif ch == b'\x1b':
                        key = 'esc'
                    elif ch == b'\x03':
                        raise KeyboardInterrupt()
                else:
                    import tty, termios, select
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    _echoed = False
                    try:
                        tty.setraw(fd)
                        ch = sys.stdin.read(1)
                        if ch == '\x1b':
                            ready, _, _ = select.select([fd], [], [], 0.05)
                            if ready:
                                ch2 = sys.stdin.read(2)
                                if ch2 == '[A': key = 'up'
                                elif ch2 == '[B': key = 'down'
                            else:
                                key = 'esc'
                        elif ch in ('\r', '\n'):
                            key = 'enter'
                        elif ch == '\x03':
                            raise KeyboardInterrupt()
                        elif ch in ('k', 'w', 'K', 'W'):  # vim/WASD up
                            key = 'up'
                            _echoed = True
                        elif ch in ('j', 's', 'J', 'S'):  # vim/WASD down
                            key = 'down'
                            _echoed = True
                        elif ch.isdigit() and 1 <= int(ch) <= num_options:
                            # Number shortcut: press 1-9 to jump directly
                            key = f'num_{ch}'
                            _echoed = True
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                        # Erase any character that might have been echoed by
                        # the terminal emulator (common in Termux soft keyboard)
                        if _echoed:
                            sys.stdout.write('\r\033[K')
                            sys.stdout.flush()
            except (KeyboardInterrupt, SystemExit):
                clear_menu()
                raise KeyboardInterrupt()
            except Exception:
                break

            if key == 'up':
                current_idx = (current_idx - 1) % num_options
                clear_menu()
                print_menu()
            elif key == 'down':
                current_idx = (current_idx + 1) % num_options
                clear_menu()
                print_menu()
            elif key and key.startswith('num_'):
                current_idx = int(key[-1]) - 1
                clear_menu()
                print_menu()
            elif key == 'enter':
                clear_menu()
                print(f"  {FROST_MINT}✔{RESET} Selected: {BOLD}{FROST_WHITE}{options[current_idx]['label']}{RESET}\n")
                return current_idx
            elif key == 'esc':
                clear_menu()
                print(f"  {FROST_DARK}Selection cancelled.{RESET}\n")
                return -1

        # Fallback if standard keyboard reading fails
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        print(f"  {FROST_CYAN}Select option (1-{num_options}):{RESET}")
        for i, opt in enumerate(options, 1):
            print(f"    {i}. {opt['label']} - {opt.get('description', '')}")
        ans = input(f"  Choose [1-{num_options}]: ").strip()
        if ans.isdigit() and 1 <= int(ans) <= num_options:
            return int(ans) - 1
        return -1

    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
