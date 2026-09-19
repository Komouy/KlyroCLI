"""
cli/spinner.py — Terminal UI utilities: Spinner, CancellationMonitor, Banner & Animation
"""

import os
import sys
import time
import shutil
import threading
import _thread
import re
import getpass

import file_manager
import provider_manager
from config import MODEL_KECIL, GROQ_MODEL_CEPAT
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_AQUA, FROST_ICE, FROST_MINT, FROST_INDIGO,
    FROST_WHITE, FROST_GRAY, FROST_DARK, FROST_GHOST, FROST_AMBER,
    BG_SURFACE, keycap,
    gradient_text, shimmer_gradient, clip_line, get_git_branch,
)

try:
    from prompt_toolkit import PromptSession
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


def prompt_secret(prompt_text: str) -> str:
    """Prompt user for sensitive input (like API Key) with password masking (*)."""
    if PROMPT_TOOLKIT_AVAILABLE:
        try:
            from prompt_toolkit.formatted_text import ANSI
            temp_session = PromptSession()
            return temp_session.prompt(ANSI(prompt_text), is_password=True).strip()
        except Exception:
            pass
    clean_prompt = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', prompt_text)
    try:
        return getpass.getpass(prompt=clean_prompt).strip()
    except Exception:
        return input(clean_prompt).strip()


def static_box_width(design_width: int) -> int:
    """Adaptive box width based on terminal size."""
    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    return max(20, min(design_width, term_width - 6))


class CancellationMonitor:
    """
    Background listener that monitors the ESC key (or Ctrl+C) during query streaming.
    Interrupts the main thread safely via _thread.interrupt_main(), stopping both
    blocking network waits and token generation loops cleanly.
    """
    def __init__(self):
        self.cancelled_by_esc = False
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self.cancelled_by_esc = False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self):
        if sys.platform == "win32":
            try:
                import msvcrt
                while not self._stop_event.is_set():
                    if msvcrt.kbhit():
                        ch = msvcrt.getch()
                        if ch == b'\x1b':  # ESC key
                            self.cancelled_by_esc = True
                            while msvcrt.kbhit():
                                msvcrt.getch()
                            _thread.interrupt_main()
                            break
                        elif ch == b'\x03':  # Ctrl+C
                            self.cancelled_by_esc = False
                            _thread.interrupt_main()
                            break
                    time.sleep(0.04)
            except Exception:
                pass
        else:
            try:
                import select
                import termios
                import tty
                if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
                    return
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    tty.setcbreak(fd)
                    while not self._stop_event.is_set():
                        r, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if r:
                            ch = sys.stdin.read(1)
                            if ch == '\x1b':
                                self.cancelled_by_esc = True
                                _thread.interrupt_main()
                                break
                            elif ch == '\x03':  # Ctrl+C
                                self.cancelled_by_esc = False
                                _thread.interrupt_main()
                                break
                finally:
                    try:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    except Exception:
                        pass
            except Exception:
                pass

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.15)
        if sys.platform == "win32":
            try:
                import msvcrt
                while msvcrt.kbhit():
                    msvcrt.getch()
            except Exception:
                pass


class Spinner:
    """Live terminal spinner with color gradient pulse and elapsed duration counter."""
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    COLORS = [FROST_CYAN, FROST_AQUA, FROST_ICE, FROST_INDIGO]

    def __init__(self, message="Thinking..."):
        self.message = message
        self.running = False
        self.thread = None
        self.start_time = 0.0

    def start(self):
        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def _spin(self):
        idx = 0
        while self.running:
            frame = self.FRAMES[idx % len(self.FRAMES)]
            color = self.COLORS[(idx // 2) % len(self.COLORS)]
            elapsed = time.time() - self.start_time

            term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
            time_str = f"({elapsed:.1f}s)"
            esc_str = " [ESC to cancel]"

            # 4 (prefix) + 1 (space) + 1 (space) + time + esc + 2 (buffer)
            overhead = 8 + len(time_str) + len(esc_str)
            avail_msg = max(10, term_cols - overhead)

            msg = self.message or ""
            if len(msg) > avail_msg:
                msg = msg[:max(1, avail_msg - 3)] + "..."

            time_tag = f"{FROST_DARK}{time_str}{RESET}"
            esc_hint = f"  {FROST_DARK}{esc_str}{RESET}"
            line_to_write = f"\r  {color}{frame}{RESET} {FROST_WHITE}{msg}{RESET} {time_tag}{esc_hint}\033[K"
            try:
                sys.stdout.write(line_to_write)
                sys.stdout.flush()
            except (UnicodeEncodeError, Exception):
                safe_frame = ["|", "/", "-", "\\"][idx % 4]
                safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
                sys.stdout.write(f"\r  {color}{safe_frame}{RESET} {FROST_WHITE}{safe_msg}{RESET} {time_tag}{esc_hint}\033[K")
                sys.stdout.flush()
            time.sleep(0.06)
            idx += 1

    def update(self, msg):
        self.message = msg

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def _progress_bar(label: str, pct: float, bar_color: str, width: int = 20) -> str:
    """Render a compact inline progress bar."""
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar_color}{bar}{RESET} {FROST_DARK}{int(pct*100):3d}%{RESET}  {FROST_GRAY}{label}{RESET}"


def _startup_step(
    glyph_color: str,
    label: str,
    detail_fn,
    steps: int = 8,
    delay: float = 0.022,
    bar_color: str = None,
) -> None:
    """Animate a single startup phase with spinner + progress bar, then print checkmark."""
    glyphs = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    bar_c = bar_color or glyph_color
    for i in range(steps):
        g = glyphs[i % len(glyphs)]
        pct = (i + 1) / steps
        bar = _progress_bar(label, pct, bar_c)
        sys.stdout.write(f"\r  {glyph_color}{g}{RESET}  {bar}\033[K")
        sys.stdout.flush()
        time.sleep(delay)
    detail = detail_fn()
    sys.stdout.write(f"\r  {FROST_MINT}✔{RESET}  {FROST_GRAY}{label}{RESET}  {detail}\033[K\n")
    sys.stdout.flush()


def print_banner(folder_path, ai_assistant):
    """Rich dashboard card with shimmering frost frame, pills, and keycap shortcuts."""
    import sys as _sys

    folder_name = os.path.basename(os.path.abspath(folder_path)) or folder_path
    files = file_manager.list_daftar_file(folder_path)
    provider_name = provider_manager.PROVIDER_CATALOG.get(
        ai_assistant.provider, {}
    ).get("name", ai_assistant.provider.upper())
    model_name = ai_assistant.current_model or (
        MODEL_KECIL if ai_assistant.provider == "gemini" else GROQ_MODEL_CEPAT
    )
    model_short = model_name.split("/")[-1] if "/" in model_name else model_name
    git_branch = get_git_branch(folder_path)
    has_key = bool(provider_manager.get_api_key(ai_assistant.provider)) if ai_assistant.provider != "custom" else True
    py_ver = f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}"

    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    card_w = max(24, min(72, term_width - 6))

    TOP = f"  {FROST_DARK}╭{'─' * card_w}╮{RESET}"
    BOT = f"  {FROST_DARK}╰{'─' * card_w}╯{RESET}"
    BAR = f"{FROST_DARK}│{RESET}"

    def row(content: str) -> str:
        return f"  {BAR}  {content}"

    def divider_row(label: str) -> str:
        label_str = f" {label} "
        pad = max(0, card_w - len(label_str) - 1)
        lpad = pad // 2
        rpad = pad - lpad
        return (
            f"  {FROST_DARK}├{'─' * lpad}{RESET}"
            f"{BG_SURFACE}{FROST_ICE}{BOLD}{label_str}{RESET}"
            f"{FROST_DARK}{'─' * rpad}┤{RESET}"
        )

    lines = [TOP]
    struct = {0}

    def add_line(text: str, structural: bool = False):
        lines.append(text)
        if structural:
            struct.add(len(lines) - 1)

    # ── WORKSPACE ──
    add_line(divider_row("WORKSPACE"), structural=True)
    add_line(row(f"{FROST_GHOST}📁 folder   {RESET}{FROST_WHITE}{BOLD}{folder_name}{RESET}"))
    add_line(row(f"{FROST_GHOST}📄 files    {RESET}{FROST_CYAN}{BOLD}{len(files)}{RESET}{FROST_DARK} files indexed{RESET}"))
    if git_branch:
        branch_color = FROST_AMBER if "*" in git_branch else FROST_MINT
        add_line(row(f"{FROST_GHOST}🌿 git      {RESET}{branch_color}{git_branch}{RESET}"))

    # ── AI ENGINE ──
    add_line(divider_row("AI ENGINE"), structural=True)
    key_status = (
        f"{FROST_MINT}● active{RESET}"
        if has_key else
        f"{FROST_AMBER}○ key missing  {FROST_DARK}/provider{RESET}"
    )
    add_line(row(f"{FROST_GHOST}🤖 provider {RESET}{FROST_INDIGO}{BOLD}{provider_name}{RESET}  {key_status}"))
    add_line(row(f"{FROST_GHOST}⚡ model    {RESET}{FROST_ICE}{model_short}{RESET}"))
    add_line(row(f"{FROST_GHOST}🐍 runtime  {RESET}{FROST_GRAY}Python {py_ver}{RESET}"))

    # ── QUICK START ──
    add_line(divider_row("QUICK START"), structural=True)
    if card_w >= 52:
        add_line(row(
            f"{FROST_GHOST}try    {RESET}"
            f"{keycap('/help')}  {keycap('/model')}  {keycap('/provider')}  {keycap('ESC')}"
        ))
    else:
        add_line(row(
            f"{keycap('/help')}{FROST_DARK} · {RESET}"
            f"{keycap('/model')}{FROST_DARK} · {RESET}"
            f"{keycap('ESC')}"
        ))

    lines.append(BOT)
    struct.add(len(lines) - 1)

    # Draw the card (clipped so no row can wrap and desync the sweep)
    print()
    for ln in lines:
        print(clip_line(ln, term_width - 1))
    # Cursor now rests on the empty line right after the bottom border.

    # ── Aurora sweep: ice-light glides along the frost frame only ──
    # NOTE: the breathing-room blank is printed AFTER the sweep — printing it
    # before would put the cursor one row too far down, and every sweep frame
    # would repaint the whole card shifted one line low, duplicating the
    # borders and section pills over the content rows (overlap bug).
    n = len(lines)
    for sweep in range(5):
        center = -0.3 + (1.6 * sweep / 4)
        sys.stdout.write(f"\033[{n}F\r")
        for i, ln in enumerate(lines):
            if i in struct:
                ln = shimmer_gradient(ln, (71, 85, 105), (129, 140, 248), center=center)
            sys.stdout.write(clip_line(ln, term_width - 1) + "\n")
        sys.stdout.flush()
        time.sleep(0.05)
    print()  # breathing room — after the sweep so cursor math stays anchored


def play_startup_animation(folder_path, ai_assistant):
    """Lively startup intro: gradient logo + ice-light shimmer sweep and micro-step ticker."""
    files = file_manager.list_daftar_file(folder_path)
    os.system("cls" if sys.platform == "win32" else "clear")

    logo_lines = [
        "██╗  ██╗██╗  ██╗   ██╗██████╗  ██████╗ ",
        "██║ ██╔╝██║  ╚██╗ ██╔╝██╔══██╗██╔═══██╗",
        "█████╔╝ ██║   ╚████╔╝ ██████╔╝██║   ██║",
        "██╔═██╗ ██║    ╚██╔╝  ██╔══██╗██║   ██║",
        "██║  ██╗███████╗██║   ██║  ██║╚██████╔╝",
        "╚═╝  ╚═╝╚══════╝╚═╝   ╚═╝  ╚═╝ ╚═════╝ ",
    ]

    palette_shifts = [
        ((56, 189, 248), (129, 140, 248)),
        ((34, 211, 238), (168, 85, 247)),
        ((56, 189, 248), (52, 211, 153)),
    ]

    start_c, end_c = palette_shifts[0]
    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    print()
    if term_width >= 45:
        for line in logo_lines:
            print("  " + gradient_text(line, start_c, end_c))
        sys.stdout.flush()

        # ── Nordic shimmer sweep: an ice-light band glides across the logo ──
        for sweep in range(7):
            center = -0.35 + (1.7 * sweep / 6)
            sys.stdout.write("\033[6F\r")
            for line in logo_lines:
                sys.stdout.write(
                    "  " + shimmer_gradient(
                        line, start_c, end_c,
                        center=center, highlight_rgb=(224, 247, 255),
                    ) + "\n"
                )
            sys.stdout.flush()
            time.sleep(0.05)

        tagline = f"  {FROST_DARK}Autonomous Agentic CLI Coding Assistant • v2.5{RESET}"
    else:
        # Compact title for narrow mobile/Termux screens
        print("  " + gradient_text("⚡ K L Y R O   C L I ⚡", start_c, end_c))
        tagline = f"  {FROST_DARK}Autonomous Agentic CLI • v2.5{RESET}"
    print(tagline)
    print()

    # Step 1: Runtime
    spinner_glyphs = ["⠋", "⠙", "⠹", "⠸"]
    for g in spinner_glyphs:
        sys.stdout.write(clip_line(f"\r  {FROST_CYAN}{g}{RESET} {FROST_GRAY}Initializing Nordic runtime environment...{RESET}\033[K", term_width - 1))
        sys.stdout.flush()
        time.sleep(0.02)
    sys.stdout.write(clip_line(f"\r  {FROST_MINT}✔{RESET} {FROST_GRAY}Nordic runtime active{RESET}\033[K\n", term_width - 1))

    # Step 2: Indexing
    for g in spinner_glyphs:
        sys.stdout.write(clip_line(f"\r  {FROST_AQUA}{g}{RESET} {FROST_GRAY}Indexing workspace files & project context...{RESET}\033[K", term_width - 1))
        sys.stdout.flush()
        time.sleep(0.02)
    sys.stdout.write(clip_line(f"\r  {FROST_MINT}✔{RESET} {FROST_GRAY}Indexed {BOLD}{len(files)}{RESET} {FROST_GRAY}files in workspace{RESET}\033[K\n", term_width - 1))

    # Step 3: AI Provider Link
    provider_name = ai_assistant.provider.upper()
    model_name = ai_assistant.current_model or (MODEL_KECIL if ai_assistant.provider == "gemini" else GROQ_MODEL_CEPAT)
    has_key = bool(provider_manager.get_api_key(ai_assistant.provider)) if ai_assistant.provider != "custom" else True
    for g in spinner_glyphs:
        sys.stdout.write(clip_line(f"\r  {FROST_INDIGO}{g}{RESET} {FROST_GRAY}Checking AI neural engine ({provider_name})...{RESET}\033[K", term_width - 1))
        sys.stdout.flush()
        time.sleep(0.02)
    if has_key:
        sys.stdout.write(clip_line(f"\r  {FROST_MINT}✔{RESET} {FROST_GRAY}Neural engine ready:{RESET} {FROST_INDIGO}{BOLD}{provider_name}{RESET} {FROST_DARK}({model_name}){RESET}\033[K\n", term_width - 1))
    else:
        sys.stdout.write(clip_line(f"\r  {FROST_AMBER}○{RESET} {FROST_GRAY}Neural engine:{RESET} {FROST_INDIGO}{BOLD}{provider_name}{RESET} {FROST_AMBER}(Key belum diset — ketik /provider){RESET}\033[K\n", term_width - 1))

    print_banner(folder_path, ai_assistant)
