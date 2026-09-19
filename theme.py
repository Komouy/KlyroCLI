import os
import re
import sys
import time
import shutil
import unicodedata

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def display_width(text: str) -> int:
    """Visible column count: ignore ANSI, treat fullwidth as 2, combining as 0."""
    if not text:
        return 0
    plain = _ANSI_RE.sub("", text)
    width = 0
    for ch in plain:
        if unicodedata.combining(ch):
            continue
        ea = unicodedata.east_asian_width(ch)
        width += 2 if ea in ("F", "W") else 1
    return width


def wrap_by_display_width(text: str, max_width: int) -> list:
    """Split text into chunks whose display_width is at most max_width."""
    if max_width < 8:
        max_width = 8
    if not text:
        return [""]
    chunks = []
    current = []
    w = 0
    for ch in text:
        cw = display_width(ch)
        if current and w + cw > max_width:
            chunks.append("".join(current))
            current = [ch]
            w = cw
        else:
            current.append(ch)
            w += cw
    if current:
        chunks.append("".join(current))
    return chunks or [""]


# Aktifkan dukungan warna ANSI dan UTF-8 di Windows Console
if sys.platform == "win32":
    os.system("")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
# ANSI MODIFIERS
# ─────────────────────────────────────────────────────────────
RESET     = "\033[0m"
BOLD      = "\033[1m"
DIM       = "\033[2m"
ITALIC    = "\033[3m"
UNDERLINE = "\033[4m"
BLINK     = "\033[5m"
REVERSE   = "\033[7m"

# ─────────────────────────────────────────────────────────────
# NORDIC FROST 2.0 TRUECOLOR PALETTE (24-bit RGB)
# ─────────────────────────────────────────────────────────────
FROST_CYAN   = "\033[38;2;56;189;248m"    # #38bdf8 Ice Cyan / Primary accent
FROST_AQUA   = "\033[38;2;34;211;238m"    # #22d3ee Aqua Frost
FROST_ICE    = "\033[38;2;186;230;253m"   # #bae6fd Light Ice / Highlights
FROST_MINT   = "\033[38;2;52;211;153m"    # #34d399 Mint / Success, active
FROST_INDIGO = "\033[38;2;129;140;248m"   # #818cf8 Soft Indigo / Provider labels
FROST_PURPLE = "\033[38;2;168;85;247m"    # #a855f7 Royal Purple
FROST_CORAL  = "\033[38;2;248;113;113m"   # #f87171 Coral / Error
FROST_AMBER  = "\033[38;2;251;191;36m"    # #fbbf24 Warm Amber / Warning
FROST_WHITE  = "\033[38;2;241;245;249m"   # #f1f5f9 Bright Slate White
FROST_GRAY   = "\033[38;2;148;163;184m"   # #94a3b8 Muted text
FROST_DARK   = "\033[38;2;71;85;105m"     # #475569 Borders & subtle dividers
FROST_GHOST  = "\033[38;2;100;116;139m"   # #64748b Ghost / Path labels
FROST_PITCH  = "\033[38;2;15;23;42m"      # #0f172a Pitch slate (darkest)

# Background Tints
BG_PITCH     = "\033[48;2;15;23;42m"      # #0f172a Dark card background
BG_SURFACE   = "\033[48;2;30;41;59m"      # #1e293b Slate surface
BG_CYAN_TINT = "\033[48;2;8;47;73m"       # #082f49 Deep Cyan tint
BG_MINT_TINT = "\033[48;2;6;78;59m"       # #064e3b Deep Mint tint
BG_CORAL_TINT= "\033[48;2;127;29;29m"     # #7f1d1d Deep Coral tint
BG_DIFF_ADD  = "\033[48;2;6;78;59m"
BG_DIFF_DEL  = "\033[48;2;127;29;29m"
BG_CARD      = BG_PITCH

# Backward Compatibility aliases
CYAN      = FROST_CYAN
WHITE     = FROST_WHITE
GRAY      = FROST_GRAY
DARK_GRAY = FROST_DARK
GREEN     = FROST_MINT
RED       = FROST_CORAL
YELLOW    = FROST_ICE
PURPLE    = FROST_INDIGO

# ─────────────────────────────────────────────────────────────
# COLOR HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────
def cyan(text): return f"{FROST_CYAN}{text}{RESET}"
def aqua(text): return f"{FROST_AQUA}{text}{RESET}"
def ice(text): return f"{FROST_ICE}{text}{RESET}"
def mint(text): return f"{FROST_MINT}{text}{RESET}"
def indigo(text): return f"{FROST_INDIGO}{text}{RESET}"
def purple(text): return f"{FROST_PURPLE}{text}{RESET}"
def coral(text): return f"{FROST_CORAL}{text}{RESET}"
def amber(text): return f"{FROST_AMBER}{text}{RESET}"
def white(text): return f"{FROST_WHITE}{text}{RESET}"
def bold_white(text): return f"{BOLD}{FROST_WHITE}{text}{RESET}"
def yellow(text): return f"{FROST_AMBER}{text}{RESET}"
def bold_yellow(text): return f"{BOLD}{FROST_AMBER}{text}{RESET}"
def warm_yellow(text): return f"{FROST_ICE}{text}{RESET}"
def muted(text): return f"{FROST_GRAY}{text}{RESET}"
def dim(text): return f"{FROST_DARK}{text}{RESET}"
def ghost(text): return f"{FROST_GHOST}{text}{RESET}"

# ─────────────────────────────────────────────────────────────
# GRADIENT ENGINE
# ─────────────────────────────────────────────────────────────
def rgb_color(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def gradient_text(text: str, start_rgb=(56, 189, 248), end_rgb=(168, 85, 247)) -> str:
    """Renders text with a smooth 24-bit TrueColor gradient."""
    if not text:
        return ""
    length = len(text)
    if length == 1:
        return f"{rgb_color(*start_rgb)}{text}{RESET}"
    
    out = []
    sr, sg, sb = start_rgb
    er, eg, eb = end_rgb
    for i, char in enumerate(text):
        ratio = i / (length - 1)
        r = int(sr + (er - sr) * ratio)
        g = int(sg + (eg - sg) * ratio)
        b = int(sb + (eb - sb) * ratio)
        out.append(f"{rgb_color(r, g, b)}{char}")
    out.append(RESET)
    return "".join(out)

# ─────────────────────────────────────────────────────────────
# MOTION ENGINE — traveling light bands & easing
# ─────────────────────────────────────────────────────────────
def lerp_rgb(a: tuple, b: tuple, t: float) -> tuple:
    """Linear interpolation between two RGB tuples (t clamped to 0..1)."""
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def strip_ansi(text: str) -> str:
    """Remove ANSI SGR sequences from text."""
    return _ANSI_RE.sub("", text)


def shimmer_gradient(
    text: str,
    start_rgb: tuple = (56, 189, 248),
    end_rgb: tuple = (168, 85, 247),
    center: float = 0.0,
    halfwidth: float = 0.16,
    highlight_rgb: tuple = (224, 247, 255),
) -> str:
    """
    Renders text with its base gradient PLUS a traveling ice-light band.
    `center` is the band position as a 0..1 ratio across the text; characters
    near the band glow toward `highlight_rgb`. Animate by sweeping `center`
    from -0.3 to 1.3 across frames for a frosted shimmer sweep.

    ANSI-aware: embedded SGR tokens pass through untouched and only visible
    characters count toward band position — so already-colored lines (cards,
    banners, borders) can be shimmered without breaking their styling.
    """
    if not text:
        return ""
    tokens = re.split(r"(\033\[[0-9;]*m)", text)
    total = sum(len(t) for t in tokens if t and not _ANSI_RE.fullmatch(t))
    if total == 0:
        return text
    out = []
    seen = 0
    for tok in tokens:
        if not tok:
            continue
        if _ANSI_RE.fullmatch(tok):
            out.append(tok)
            continue
        for ch in tok:
            pos = seen / max(1, total - 1)
            color = lerp_rgb(start_rgb, end_rgb, pos)
            dist = abs(pos - center)
            if dist < halfwidth:
                glow = 1.0 - (dist / halfwidth)
                color = lerp_rgb(color, highlight_rgb, glow * glow)  # ease-in glow
            out.append(f"{rgb_color(*color)}{ch}")
            seen += 1
    out.append(RESET)
    return "".join(out)


def shimmer_text(
    text: str,
    base_rgb: tuple = (56, 189, 248),
    highlight_rgb: tuple = (186, 230, 253),
    center: float = 0.0,
    halfwidth: float = 0.18,
) -> str:
    """Flat-color variant of shimmer_gradient: constant base, moving glow band."""
    return shimmer_gradient(
        text, base_rgb, base_rgb, center=center,
        halfwidth=halfwidth, highlight_rgb=highlight_rgb,
    )


# ─────────────────────────────────────────────────────────────
# UI COMPONENTS & BADGES
# ─────────────────────────────────────────────────────────────
ICON_AI      = f"{FROST_CYAN}[AI]{RESET}"
ICON_DIR     = f"{FROST_INDIGO}[DIR]{RESET}"
ICON_FILE    = f"{FROST_WHITE}[FILE]{RESET}"
ICON_OK      = f"{FROST_MINT}[OK]{RESET}"
ICON_WARN    = f"{FROST_AMBER}[WARN]{RESET}"
ICON_ERR     = f"{FROST_CORAL}[ERROR]{RESET}"
ICON_SCAN    = f"{FROST_CYAN}[SCAN]{RESET}"
ICON_EDIT    = f"{FROST_ICE}[EDIT]{RESET}"
ICON_TERM    = f"{FROST_INDIGO}[TERM]{RESET}"
ICON_RESTORE = f"{FROST_WHITE}[RESTORE]{RESET}"
ICON_PROMPT  = f"{FROST_CYAN}❯{RESET}"
ICON_BULLET  = f"{FROST_DARK}·{RESET}"

def badge(text: str, fg=FROST_CYAN, bg=BG_CYAN_TINT) -> str:
    """Renders a stylish pill badge."""
    return f"{bg}{fg}{BOLD} {text} {RESET}"

def keycap(key: str) -> str:
    """Renders a keyboard keycap badge."""
    return f"{BG_SURFACE}{FROST_ICE}{BOLD} {key} {RESET}"

def get_git_branch(cwd: str = ".") -> str:
    """Detect git branch name and uncommitted status cleanly."""
    try:
        import subprocess
        res = subprocess.run(
            "git branch --show-current",
            shell=True, cwd=cwd, capture_output=True, text=True, timeout=1
        )
        branch = res.stdout.strip()
        if not branch:
            return ""
        # Check dirty
        status_res = subprocess.run(
            "git status --porcelain",
            shell=True, cwd=cwd, capture_output=True, text=True, timeout=1
        )
        dirty_count = len(status_res.stdout.strip().splitlines()) if status_res.stdout.strip() else 0
        if dirty_count > 0:
            return f"🌿 {branch} *{dirty_count}"
        return f"🌿 {branch}"
    except Exception:
        return ""


class UI:
    """Centralized UI/UX Abstraction Layer for Klyro Code (Nordic Frost style)."""

    @staticmethod
    def success(message: str):
        """Render general success action."""
        print(f"  {FROST_MINT}✓{RESET} {message}")

    @staticmethod
    def error(message: str):
        """Render error or access denied message."""
        print(f"  {FROST_CORAL}✗{RESET} {FROST_WHITE}{message}{RESET}")

    @staticmethod
    def warning(message: str):
        """Render warnings uniformly."""
        print(f"  {FROST_CORAL}{BOLD}⚠️  WARNING:{RESET} {FROST_WHITE}{message}{RESET}")

    @staticmethod
    def info(message: str):
        """Render informational notifications."""
        print(f"  {FROST_CYAN}ℹ{RESET} {FROST_WHITE}{message}{RESET}")

    # --- MICRO-RHYTHM ---
    @staticmethod
    def _beat(delay: float = 0.03):
        """Tiny pause that gives multi-line outputs a soft entrance rhythm."""
        time.sleep(delay)

    # --- SEMANTIC FILE OPERATIONS ---
    @staticmethod
    def file_created(filename: str):
        """Renders: 
        ✦ Created
        └── filename
        """
        print(f"  {FROST_MINT}{BOLD}✦{RESET} {BOLD}Created{RESET}")
        UI._beat()
        print(f"  {FROST_DARK}└──{RESET} {FROST_WHITE}{filename}{RESET}")

    @staticmethod
    def file_updated(filename: str):
        """Renders:
        ✦ Updated
        └── filename
        """
        print(f"  {FROST_MINT}{BOLD}✦{RESET} {BOLD}Updated{RESET}")
        UI._beat()
        print(f"  {FROST_DARK}└──{RESET} {FROST_WHITE}{filename}{RESET}")

    @staticmethod
    def file_deleted(filename: str):
        """Renders:
        ✦ Deleted
        └── filename
        """
        print(f"  {FROST_CORAL}{BOLD}✦{RESET} {BOLD}Deleted{RESET}")
        UI._beat()
        print(f"  {FROST_DARK}└──{RESET} {FROST_WHITE}{filename}{RESET}")

    @staticmethod
    def folder_created(foldername: str):
        """Renders:
        ✦ Created directory
        └── foldername
        """
        print(f"  {FROST_MINT}{BOLD}✦{RESET} {BOLD}Created directory{RESET}")
        UI._beat()
        print(f"  {FROST_DARK}└──{RESET} {FROST_WHITE}{foldername}{RESET}")

    @staticmethod
    def file_renamed(src: str, dst: str):
        """Renders:
        ✦ Renamed
        └── src → dst
        """
        print(f"  {FROST_MINT}{BOLD}✦{RESET} {BOLD}Renamed{RESET}")
        UI._beat()
        print(f"  {FROST_DARK}└──{RESET} {FROST_WHITE}{src}{RESET} {FROST_DARK}→{RESET} {FROST_WHITE}{dst}{RESET}")

    @staticmethod
    def syntax_warning(filename: str, syntax_msg: str):
        """Renders syntax validation results."""
        print(f"  {FROST_AMBER}⚠ Syntax:{RESET} {FROST_WHITE}{syntax_msg}{RESET}")
        UI._beat()
        print(f"  {FROST_DARK}└── File is on disk — fix it before running.{RESET}")

    @staticmethod
    def step(action: str, target: str):
        """Renders action step like starting a background process."""
        print(f"  {FROST_CYAN}⚡{RESET} {FROST_GRAY}{action}:{RESET} {FROST_WHITE}{target}{RESET}")

    # --- FRAMED COMPONENT CARDS ---
    @staticmethod
    def card_start(title: str, subtitle: str = None, border_color: str = FROST_DARK, box_width: int = 60):
        title_str = f"● {title}"
        if subtitle:
            title_str += f" {subtitle}"
        print(f"\n  {FROST_CYAN}{title_str}{RESET}")
        print(f"  {border_color}╭{'─' * box_width}╮{RESET}")

    @staticmethod
    def card_line(body: str, marker: str = " ", color: str = "", border_color: str = FROST_DARK, box_width: int = 60):
        """Body row inside the card: wraps text and closes the right border so
        the frame reads as a full box. `marker` colors the leading glyph."""
        inner = max(8, box_width - 2)
        chunks = wrap_by_display_width(body, inner - 1)
        for idx, chunk in enumerate(chunks):
            lead = marker if idx == 0 else "↳"
            pad = " " * max(0, inner - 1 - display_width(chunk))
            print(
                f"  {border_color}│{RESET} {color}{lead}{chunk}{pad}{RESET} {border_color}│{RESET}"
            )

    @staticmethod
    def card_end(border_color: str = FROST_DARK, box_width: int = 60):
        print(f"  {border_color}╰{'─' * box_width}╯{RESET}\n")


