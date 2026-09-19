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
    gradient_text, get_git_branch,
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


def print_banner(folder_path, ai_assistant):
    """Render sleek modern dashboard banner with rounded card and git branch detection."""
    folder_name = os.path.basename(os.path.abspath(folder_path)) or folder_path
    files = file_manager.list_daftar_file(folder_path)
    provider_name = ai_assistant.provider.upper()
    model_name = ai_assistant.current_model or (MODEL_KECIL if ai_assistant.provider == "gemini" else GROQ_MODEL_CEPAT)
    git_branch = get_git_branch(folder_path)

    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    card_w = max(24, min(68, term_width - 6))

    BAR = f"{FROST_DARK}│{RESET}"
    top_border = f"  {FROST_DARK}╭{'─'*card_w}╮{RESET}"
    bot_border = f"  {FROST_DARK}╰{'─'*card_w}╯{RESET}"

    git_line = ""
    if git_branch:
        git_line = f"\n  {BAR}  {FROST_GHOST}git branch{RESET}  {FROST_MINT}{git_branch}{RESET}"

    print(f"\n{top_border}")
    if card_w < 44:
        # Compact display for mobile / narrow terminals (e.g. Termux portrait)
        print(f"  {BAR}  {FROST_GHOST}ws {RESET}  {FROST_WHITE}{BOLD}{folder_name}{RESET} {FROST_DARK}({len(files)}f){RESET}{git_line}")
        print(f"  {BAR}  {FROST_GHOST}ai {RESET}  {FROST_INDIGO}{BOLD}{provider_name}{RESET} {FROST_DARK}·{RESET} {FROST_ICE}{model_name[:16]}{RESET}")
        print(f"  {BAR}  {FROST_DARK}Type or {FROST_CYAN}/help{FROST_DARK} for commands{RESET}")
    else:
        print(f"  {BAR}  {FROST_GHOST}workspace {RESET}  {FROST_WHITE}{BOLD}{folder_name}{RESET} {FROST_DARK}({len(files)} files indexed){RESET}{git_line}")
        print(f"  {BAR}  {FROST_GHOST}ai engine {RESET}  {FROST_INDIGO}{BOLD}{provider_name}{RESET} {FROST_DARK}·{RESET} {FROST_ICE}{model_name}{RESET}")
        print(f"  {BAR}  {FROST_DARK}Type anything to code, or {FROST_CYAN}/help{FROST_DARK} for command palette{RESET}")
    print(f"{bot_border}\n")


def play_startup_animation(folder_path, ai_assistant):
    """Lively startup intro animation with sweeping gradient ASCII logo and micro-step ticker."""
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
        sys.stdout.write(f"\r  {FROST_CYAN}{g}{RESET} {FROST_GRAY}Initializing Nordic runtime environment...{RESET}\033[K")
        sys.stdout.flush()
        time.sleep(0.02)
    sys.stdout.write(f"\r  {FROST_MINT}✔{RESET} {FROST_GRAY}Nordic runtime active{RESET}\033[K\n")

    # Step 2: Indexing
    for g in spinner_glyphs:
        sys.stdout.write(f"\r  {FROST_AQUA}{g}{RESET} {FROST_GRAY}Indexing workspace files & project context...{RESET}\033[K")
        sys.stdout.flush()
        time.sleep(0.02)
    sys.stdout.write(f"\r  {FROST_MINT}✔{RESET} {FROST_GRAY}Indexed {BOLD}{len(files)}{RESET} {FROST_GRAY}files in workspace{RESET}\033[K\n")

    # Step 3: AI Provider Link
    provider_name = ai_assistant.provider.upper()
    model_name = ai_assistant.current_model or (MODEL_KECIL if ai_assistant.provider == "gemini" else GROQ_MODEL_CEPAT)
    has_key = bool(provider_manager.get_api_key(ai_assistant.provider)) if ai_assistant.provider != "custom" else True
    for g in spinner_glyphs:
        sys.stdout.write(f"\r  {FROST_INDIGO}{g}{RESET} {FROST_GRAY}Checking AI neural engine ({provider_name})...{RESET}\033[K")
        sys.stdout.flush()
        time.sleep(0.02)
    if has_key:
        sys.stdout.write(f"\r  {FROST_MINT}✔{RESET} {FROST_GRAY}Neural engine ready:{RESET} {FROST_INDIGO}{BOLD}{provider_name}{RESET} {FROST_DARK}({model_name}){RESET}\033[K\n")
    else:
        sys.stdout.write(f"\r  {FROST_AMBER}○{RESET} {FROST_GRAY}Neural engine:{RESET} {FROST_INDIGO}{BOLD}{provider_name}{RESET} {FROST_AMBER}(Key belum diset — ketik /provider){RESET}\033[K\n")

    print_banner(folder_path, ai_assistant)
