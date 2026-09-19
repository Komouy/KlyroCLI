"""
cli/interactive_menu.py — Arrow-key navigable card menu for model & option selection.

Nordic Frost motion design:
  • Cascade entrance — options ripple in from the top on first reveal
  • Glide transition — a ghost arrow trails the row just left for one settle frame
  • Idle shimmer — a soft ice-light band sweeps across the menu title while waiting
"""

import sys
import time

from cli.spinner import static_box_width
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_ICE, FROST_MINT,
    FROST_WHITE, FROST_GRAY, FROST_DARK, FROST_GHOST,
    BG_CYAN_TINT,
    keycap, shimmer_gradient, clip_line, display_width,
)

# ── Motion tuning ────────────────────────────────────────────
_ENTRANCE_DELAY = 0.014   # per-row stagger during the first reveal
_SETTLE_DELAY   = 0.05    # glide frame hold when the selection moves
_SHIMMER_EVERY  = 0.07    # idle shimmer tick interval (seconds)
_SHIMMER_STEP   = 0.09    # band travel per tick (0..1 across the title)

_TITLE_BASE = (56, 189, 248)    # FROST_CYAN
_TITLE_END  = (129, 140, 248)   # FROST_INDIGO
_TITLE_GLOW = (224, 247, 255)   # glacial white highlight


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
    shimmer = {"center": -0.35}

    # ── Rendering helpers ─────────────────────────────────────
    def title_fragment(center=None) -> str:
        if center is None:
            return f"{FROST_CYAN}{BOLD}{title}{RESET}"
        return shimmer_gradient(
            title, _TITLE_BASE, _TITLE_END,
            center=center, highlight_rgb=_TITLE_GLOW,
        )

    def write_title_bar(center=None, newline=True):
        """Emit the top border + (optionally shimmering) title line.
        With newline=False the cursor stays on this line — used by the idle
        shimmer tick so its line-count arithmetic stays anchored."""
        pad = card_width - len(title) - 5
        line = (
            f"  {FROST_DARK}╭─ {title_fragment(center)}"
            f" {FROST_DARK}{'─' * max(0, pad)}╮{RESET}\033[K"
        )
        sys.stdout.write(clip_line(line, card_width + 4) + ("\n" if newline else ""))

    def render_row(idx: int, selected: bool, ghost: bool = False) -> str:
        opt = options[idx]
        label = opt["label"][:24].ljust(24)
        # Keep every row inside the card so it can never wrap — a wrapped row
        # would desync clear_menu()'s cursor arithmetic and overwrite other UI.
        desc_budget = max(0, card_width - 34)
        desc = opt.get("description", "")
        if len(desc) > desc_budget:
            desc = desc[:max(0, desc_budget - 1)] + "…"
        if selected:
            arrow = f"{FROST_CYAN}{BOLD}❯{RESET}"
            body = (
                f"{BG_CYAN_TINT} {BOLD}{FROST_WHITE}{label} {RESET}"
                f"  {FROST_ICE}{desc}{RESET}"
            )
            return f"  {FROST_DARK}│{RESET} {arrow} {body}"
        if ghost:
            # glide trail: the row the selection just left
            return (
                f"  {FROST_DARK}│{RESET}  {FROST_DARK}·{RESET} "
                f"{FROST_GRAY}{label}{RESET} {FROST_DARK}{desc}{RESET}"
            )
        return (
            f"  {FROST_DARK}│{RESET}   "
            f"{FROST_GHOST}{label}{RESET} {FROST_DARK}{desc}{RESET}"
        )

    def render(shimmer_center=None, ghost_idx=None, first=False):
        """Draw the full menu. With first=True, cascade rows in one by one."""
        sys.stdout.write("\n")
        sys.stdout.flush()
        write_title_bar(shimmer_center)
        for idx in range(num_options):
            is_selected = idx == current_idx
            is_ghost = ghost_idx is not None and idx == ghost_idx and not is_selected
            sys.stdout.write(clip_line(render_row(idx, is_selected, is_ghost), card_width + 4) + "\n")
            if first:
                sys.stdout.flush()
                time.sleep(_ENTRANCE_DELAY)
        sys.stdout.write(clip_line(f"  {FROST_DARK}╰{'─' * card_width}╯{RESET}", card_width + 4) + "\n")
        sys.stdout.write(clip_line(
            f"  {keycap('↑/↓')} {FROST_DARK}Navigate{RESET}  "
            f"{keycap('Enter')} {FROST_DARK}Select{RESET}  "
            f"{keycap('Esc')} {FROST_DARK}Cancel{RESET}",
            card_width + 4,
        ) + "\n")
        sys.stdout.flush()

    def tick_shimmer():
        """Advance the idle ice-light band across the title line in place."""
        shimmer["center"] += _SHIMMER_STEP
        if shimmer["center"] > 1.35:
            shimmer["center"] = -0.35
        # Cursor sits on the empty line BELOW the hint (render ends with \n).
        # Title row is N+3 lines up: hint, bottom border, N options, title.
        sys.stdout.write(f"\033[{num_options + 3}F\r")
        write_title_bar(shimmer["center"], newline=False)
        # Return to the same anchored row so navigation redraws stay put
        sys.stdout.write(f"\033[{num_options + 3}B")
        sys.stdout.flush()

    def clear_menu():
        # lines: 1 blank + 1 top-border + N options + 1 bottom-border + 1 hint
        lines_to_clear = num_options + 4
        for _ in range(lines_to_clear):
            sys.stdout.write("\033[F\033[K")
        sys.stdout.flush()

    def glide_to(prev_idx):
        """Two-frame selection transition: ghost trail frame, then settle."""
        clear_menu()
        render(ghost_idx=prev_idx)
        time.sleep(_SETTLE_DELAY)
        clear_menu()
        render()

    # ── Key input with idle shimmer ───────────────────────────
    def read_key():
        """Blocking key read; shimmers the title while waiting. Returns key id."""
        if sys.platform == "win32":
            import msvcrt
            last_tick = time.time()
            while not msvcrt.kbhit():
                now = time.time()
                if now - last_tick >= _SHIMMER_EVERY:
                    tick_shimmer()
                    last_tick = now
                time.sleep(0.02)
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ch2 = msvcrt.getch()
                if ch2 == b"H":
                    return "up"
                if ch2 == b"P":
                    return "down"
                return None
            if ch == b"\r":
                return "enter"
            if ch == b"\x1b":
                return "esc"
            if ch == b"\x03":
                raise KeyboardInterrupt()
            c = ch.decode(errors="ignore")
            if c in ("k", "w", "K", "W"):
                return "up"
            if c in ("j", "s", "J", "S"):
                return "down"
            if c.isdigit() and 1 <= int(c) <= num_options:
                return f"num_{c}"
            return None

        # POSIX / Termux
        import tty, termios, select
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        _echoed = False
        try:
            tty.setraw(fd)
            ch = None
            while ch is None:
                ready, _, _ = select.select([fd], [], [], _SHIMMER_EVERY)
                if ready:
                    ch = sys.stdin.read(1)
                else:
                    tick_shimmer()
            if ch == "\x1b":
                ready, _, _ = select.select([fd], [], [], 0.05)
                if ready:
                    ch2 = sys.stdin.read(2)
                    if ch2 == "[A":
                        return "up"
                    if ch2 == "[B":
                        return "down"
                return "esc"
            if ch in ("\r", "\n"):
                return "enter"
            if ch == "\x03":
                raise KeyboardInterrupt()
            if ch in ("k", "w", "K", "W"):  # vim/WASD up
                _echoed = True
                return "up"
            if ch in ("j", "s", "J", "S"):  # vim/WASD down
                _echoed = True
                return "down"
            if ch.isdigit() and 1 <= int(ch) <= num_options:
                _echoed = True
                return f"num_{ch}"
            return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            # Erase any character that might have been echoed by
            # the terminal emulator (common in Termux soft keyboard)
            if _echoed:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()



    try:
        render(first=True)
        while True:
            try:
                key = read_key()
            except (KeyboardInterrupt, SystemExit):
                clear_menu()
                raise KeyboardInterrupt()
            except Exception:
                break

            if key in ("up", "down") or (key and key.startswith("num_")):
                prev_idx = current_idx
                if key == "up":
                    current_idx = (current_idx - 1) % num_options
                elif key == "down":
                    current_idx = (current_idx + 1) % num_options
                else:
                    current_idx = int(key[-1]) - 1
                if current_idx != prev_idx:
                    glide_to(prev_idx)
                else:
                    clear_menu()
                    render()
            elif key == "enter":
                clear_menu()
                print(
                    f"  {FROST_MINT}✔{RESET} Selected: "
                    f"{BOLD}{FROST_WHITE}{options[current_idx]['label']}{RESET}\n"
                )
                return current_idx
            elif key == "esc":
                clear_menu()
                print(f"  {FROST_DARK}Selection cancelled.{RESET}\n")
                return -1
            # key is None → unrecognised key, keep waiting

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
