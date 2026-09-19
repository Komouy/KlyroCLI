import time
from file_manager import _parse_fence_line, _filename_from_fence_info
from theme import (
    FROST_WHITE, FROST_CYAN, FROST_DARK, FROST_ICE, FROST_GHOST, FROST_MINT,
    RESET, BOLD, shimmer_text, clip_line,
)
import shutil


def _clip(s: str) -> str:
    """Keep in-place-rewritten lines to a single physical row."""
    return clip_line(s, shutil.get_terminal_size(fallback=(80, 24)).columns - 1)

# ANSI: carriage-return + erase entire line (overwrites placeholder)
_ERASE_LINE = "\r\033[2K"
_SPINNERS = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class CommentStripper:
    """Buffers and strips HTML comments (like <!--ACTION...-->) from active streams."""
    def __init__(self):
        self.buffer = ""
        self.in_comment = False
        self.comment_buf = ""

    def feed(self, chunk: str) -> str:
        out = []
        for char in chunk:
            if not self.in_comment:
                self.buffer += char
                if "<!--".startswith(self.buffer):
                    if self.buffer == "<!--":
                        self.in_comment = True
                        self.buffer = ""
                else:
                    out.append(self.buffer)
                    self.buffer = ""
            else:
                self.comment_buf += char
                if self.comment_buf.endswith("-->"):
                    self.in_comment = False
                    self.comment_buf = ""
        return "".join(out)

    def flush(self) -> str:
        """Call once the stream has ended. If we're still inside an
        unclosed '<!--' (e.g. the provider's output got truncated before
        '-->' ever arrived), surface the raw fragment as visible text
        instead of silently dropping it — the user should always be able
        to see everything the model actually generated, even if it's a
        malformed/incomplete action tag."""
        if self.in_comment:
            leftover = "<!--" + self.comment_buf
            self.in_comment = False
            self.comment_buf = ""
            return leftover
        res = self.buffer
        self.buffer = ""
        return res


class CodeBlockBuffer:
    """
    Hides code fence content while the AI is streaming it, then reveals the
    complete block with a styled header once the closing fence arrives.

    Prose outside fences passes through immediately, character by character,
    exactly as before.

    Usage (in the streaming loop):
        stripper = CommentStripper()
        code_buf = CodeBlockBuffer()
    If live_counter=True, streams an in-place shimmer and line count indicator
    while code lines are buffered.
    """

    def __init__(self, live_counter: bool = False):
        self._hold: str = ""          # partial-line buffer
        self._in_fence: bool = False
        self._fence_tick_len: int = 0
        self._fence_tick_char: str = "`"
        self._fence_info: str = ""    # e.g. "python:main.py" or "python"
        self._code_lines: list = []   # buffered lines inside the fence
        self._inner_depth: int = 0    # depth of nested inner fences (e.g. ```bash inside markdown)
        self._placeholder_shown: bool = False
        self._live_counter: bool = live_counter
        self._frame_idx: int = 0

    # ── Public API ────────────────────────────────────────────────

    def feed(self, chunk: str) -> str:
        """Feed a stripped chunk; returns text to write to stdout (may be empty)."""
        if not chunk:
            return ""
        self._hold += chunk
        out_parts = []

        # Process complete lines first
        while True:
            nl = self._hold.find("\n")
            if nl == -1:
                break
            line = self._hold[: nl + 1]
            self._hold = self._hold[nl + 1:]
            out_parts.append(self._handle_line(line))

        # Pass through partial prose line immediately so prose still feels live,
        # but hold if it could be the start of a code fence (e.g. backticks/tildes).
        if not self._in_fence and self._hold:
            if not self._maybe_incomplete_fence(self._hold):
                out_parts.append(self._hold)
                self._hold = ""

        return "".join(out_parts)

    def flush(self) -> str:
        """
        Call once after the stream ends.
        Flushes any buffered code block (truncated / no closing fence received).
        """
        out = []

        if self._hold:
            if self._in_fence:
                self._code_lines.append(self._hold)
            else:
                out.append(self._hold)
            self._hold = ""

        if self._in_fence and self._code_lines:
            # Stream ended mid-fence — reveal what we have with truncation note
            if self._placeholder_shown:
                out.append(_ERASE_LINE)
                self._placeholder_shown = False
            out.append(self._format_code_block(truncated=True))
            self._in_fence = False
            self._code_lines = []
            self._inner_depth = 0

        return "".join(out)

    def cancel(self) -> str:
        """Call if user cancels (Ctrl+C / ESC). Erases active placeholder if any."""
        if self._placeholder_shown:
            self._placeholder_shown = False
            self._in_fence = False
            self._code_lines = []
            self._inner_depth = 0
            self._hold = ""
            return _ERASE_LINE
        return ""

    # ── Internal helpers ──────────────────────────────────────────

    def _maybe_incomplete_fence(self, s: str) -> bool:
        """True if `s` could be the leading part of a fence opening line."""
        if self._in_fence:
            return False
        stripped = s.lstrip(" \t")
        if not stripped:
            return True  # only whitespace so far; could be indentation of a fence
        return stripped.startswith("`") or stripped.startswith("~")

    def _handle_line(self, line: str) -> str:
        parsed = _parse_fence_line(line)

        if parsed:
            tlen, tchar, info = parsed

            if not self._in_fence:
                # ── Opening fence detected ────────────────────────
                self._in_fence = True
                self._fence_tick_len = tlen
                self._fence_tick_char = tchar
                self._fence_info = info or ""
                self._code_lines = []
                self._inner_depth = 0
                self._placeholder_shown = True
                lang = (info.split(":")[0] if info else "code") or "code"
                # Write placeholder WITHOUT \n so cursor stays on same line;
                # \r allows the reveal step to overwrite it cleanly.
                if self._live_counter:
                    return _clip(f"  {shimmer_text('⚡ Generating', center=0.0)} {FROST_ICE}{lang}{RESET}{FROST_DARK}...{RESET} {FROST_DARK}[0 lines]{RESET}\r")
                return f"  {FROST_DARK}⏳ Generating {lang}...{RESET}\r"

            # ── We are inside a fence ─────────────────────────────
            if tchar == self._fence_tick_char and tlen >= self._fence_tick_len:
                if not info:
                    # Bare fence line: either closes an inner fence or the outer fence
                    if self._inner_depth == 0:
                        self._in_fence = False
                        result_parts = []
                        if self._placeholder_shown:
                            result_parts.append(_ERASE_LINE)
                            self._placeholder_shown = False
                        result_parts.append(self._format_code_block())
                        self._code_lines = []
                        self._fence_info = ""
                        return "".join(result_parts)
                    else:
                        self._inner_depth -= 1
                        self._code_lines.append(line)
                        return ""
                else:
                    # Fence with info string inside
                    if _filename_from_fence_info(info):
                        # A new named file fence immediately follows — finish current and start new
                        result_parts = []
                        if self._placeholder_shown:
                            result_parts.append(_ERASE_LINE)
                            self._placeholder_shown = False
                        result_parts.append(self._format_code_block())
                        self._fence_tick_len = tlen
                        self._fence_tick_char = tchar
                        self._fence_info = info
                        self._code_lines = []
                        self._inner_depth = 0
                        self._placeholder_shown = True
                        lang = (info.split(":")[0] if info else "code") or "code"
                        if self._live_counter:
                            result_parts.append(_clip(f"  {shimmer_text('⚡ Generating', center=0.0)} {FROST_ICE}{lang}{RESET}{FROST_DARK}...{RESET} {FROST_DARK}[0 lines]{RESET}\r"))
                        else:
                            result_parts.append(f"  {FROST_DARK}⏳ Generating {lang}...{RESET}\r")
                        return "".join(result_parts)
                    else:
                        # Inner language fence (e.g. ```bash inside a README block)
                        self._inner_depth += 1
                        self._code_lines.append(line)
                        return ""

            # Fence with different char/shorter length inside code
            self._code_lines.append(line)
            return ""

        if self._in_fence:
            # Regular code line — buffer silently (or update live counter)
            self._code_lines.append(line)
            if self._live_counter:
                self._frame_idx += 1
                spin = _SPINNERS[self._frame_idx % len(_SPINNERS)]
                lang = (self._fence_info.split(":")[0] if self._fence_info else "code") or "code"
                count = len(self._code_lines)
                band = shimmer_text(
                    "⚡ Generating",
                    center=((self._frame_idx % 14) / 10.0) - 0.2,
                )
                return _clip(f"\r  {FROST_ICE}{spin}{RESET} {band} {FROST_ICE}{lang}{RESET}{FROST_DARK}...{RESET} {FROST_DARK}[{count} lines]{RESET}\033[K")
            return ""

        # Normal prose line — pass through
        return line

    def _format_code_block(self, truncated: bool = False) -> str:
        info = self._fence_info or "code"
        # Width: try to fill ~52 chars of header bar
        bar_len = max(2, 48 - len(info))
        header = (
            f"  {FROST_CYAN}━━━ {BOLD}{info}{RESET}"
            f"{FROST_CYAN} {'━' * bar_len}{RESET}\n"
        )
        code_body = "".join(self._code_lines)
        if truncated:
            footer = f"  {FROST_DARK}{'─' * 30} (stream truncated){RESET}\n{FROST_WHITE}"
        else:
            footer = f"  {FROST_DARK}{'━' * 52}{RESET}\n{FROST_WHITE}"
        return header + code_body + footer


class StreamIndenter:
    """
    Ensures every line of streaming AI output has a clean left margin (2 spaces)
    so text doesn't stick to the terminal/CMD edge, while avoiding double-indentation
    when lines already have leading spaces or ANSI control codes.
    """
    def __init__(self, indent: str = "  "):
        self.indent = indent
        self.at_line_start = True
        self.leading_spaces = 0

    def feed(self, text: str) -> str:
        if not text:
            return ""
        out = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]

            if ch == "\n":
                out.append(ch)
                self.at_line_start = True
                self.leading_spaces = 0
                i += 1
                continue
            elif ch == "\r":
                out.append(ch)
                self.at_line_start = True
                self.leading_spaces = 0
                i += 1
                continue

            # Pass through ANSI escape sequences without consuming indentation state
            if ch == "\033" and i + 1 < n and text[i + 1] == "[":
                end = i + 2
                while end < n and not text[end].isalpha():
                    end += 1
                if end < n:
                    end += 1
                out.append(text[i:end])
                i = end
                continue

            if self.at_line_start:
                if ch == " ":
                    self.leading_spaces += 1
                    out.append(ch)
                    if self.leading_spaces >= len(self.indent):
                        self.at_line_start = False
                    i += 1
                    continue
                else:
                    needed = max(0, len(self.indent) - self.leading_spaces)
                    if needed > 0:
                        out.append(" " * needed)
                    out.append(ch)
                    self.at_line_start = False
                    self.leading_spaces = 0
                    i += 1
                    continue
            else:
                out.append(ch)
                i += 1

        return "".join(out)

    def reset(self):
        self.at_line_start = True
        self.leading_spaces = 0


class ThinkingStreamHandler:
    """
    Detects <think>...</think> (or <thought>...</thought>) blocks during streaming.
    Renders thought reasoning inside an elegant bordered card with dim muted styling,
    and displays execution duration upon closing.
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.in_thinking = False
        self.buffer = ""
        self.start_time = 0.0
        self.line_started = False

    def feed(self, chunk: str) -> str:
        if not self.enabled or not chunk:
            return chunk

        self.buffer += chunk
        out = []

        while self.buffer:
            if not self.in_thinking:
                idx = self.buffer.find("<think>")
                if idx == -1:
                    idx = self.buffer.find("<thought>")
                    tag_len = 9
                else:
                    tag_len = 7

                if idx != -1:
                    if idx > 0:
                        out.append(self.buffer[:idx])
                    self.in_thinking = True
                    self.start_time = time.time()
                    self.line_started = False
                    self.buffer = self.buffer[idx + tag_len:]
                    header = (
                        f"\n  {FROST_DARK}╭─{RESET} {FROST_ICE}🧠 Thinking Process{RESET} "
                        f"{FROST_DARK}{'─' * 40}{RESET}\n"
                    )
                    out.append(header)
                else:
                    possible_prefixes = ("<", "<t", "<th", "<thi", "<thin", "<think", "<tho", "<thou", "<thought")
                    ends_with_prefix = any(self.buffer.endswith(p) for p in possible_prefixes)
                    if ends_with_prefix:
                        p_match = next(p for p in sorted(possible_prefixes, key=len, reverse=True) if self.buffer.endswith(p))
                        safe_len = len(self.buffer) - len(p_match)
                        if safe_len > 0:
                            out.append(self.buffer[:safe_len])
                            self.buffer = self.buffer[safe_len:]
                        break
                    else:
                        out.append(self.buffer)
                        self.buffer = ""
            else:
                idx = self.buffer.find("</think>")
                if idx == -1:
                    idx = self.buffer.find("</thought>")
                    close_tag_len = 10
                else:
                    close_tag_len = 8

                if idx != -1:
                    thought_segment = self.buffer[:idx]
                    self.buffer = self.buffer[idx + close_tag_len:]
                    if thought_segment:
                        out.append(self._format_thought(thought_segment))
                    self.in_thinking = False
                    dur = max(0.1, time.time() - self.start_time)
                    footer = (
                        f"\n  {FROST_DARK}╰{'─' * 36} "
                        f"{FROST_MINT}✓ Thought for {dur:.1f}s{RESET} {FROST_DARK}─╯{RESET}\n\n"
                    )
                    out.append(footer)
                    self.line_started = False
                else:
                    close_prefixes = ("<", "</", "</t", "</th", "</thi", "</thin", "</think", "</tho", "</thou")
                    ends_with_prefix = any(self.buffer.endswith(p) for p in close_prefixes)
                    if ends_with_prefix:
                        p_match = next(p for p in sorted(close_prefixes, key=len, reverse=True) if self.buffer.endswith(p))
                        safe_len = len(self.buffer) - len(p_match)
                        if safe_len > 0:
                            out.append(self._format_thought(self.buffer[:safe_len]))
                            self.buffer = self.buffer[safe_len:]
                        break
                    else:
                        out.append(self._format_thought(self.buffer))
                        self.buffer = ""

        return "".join(out)

    def _format_thought(self, text: str) -> str:
        """Render thought lines with a left border and dim muted color."""
        if not text:
            return ""
        parts = []
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i > 0:
                parts.append("\n")
                self.line_started = False
            if line:
                if not self.line_started:
                    parts.append(f"  {FROST_DARK}│{RESET} {FROST_GHOST}")
                    self.line_started = True
                parts.append(line)
        return "".join(parts)

    def flush(self) -> str:
        out = []
        if self.buffer:
            if self.in_thinking:
                out.append(self._format_thought(self.buffer))
                dur = max(0.1, time.time() - self.start_time)
                out.append(f"\n  {FROST_DARK}╰{'─' * 36} {FROST_MINT}✓ Thought for {dur:.1f}s{RESET} {FROST_DARK}─╯{RESET}\n\n")
            else:
                out.append(self.buffer)
            self.buffer = ""
        elif self.in_thinking:
            dur = max(0.1, time.time() - self.start_time)
            out.append(f"\n  {FROST_DARK}╰{'─' * 36} {FROST_MINT}✓ Thought for {dur:.1f}s{RESET} {FROST_DARK}─╯{RESET}\n\n")
            self.in_thinking = False
        return "".join(out)

    def cancel(self) -> str:
        self.buffer = ""
        if self.in_thinking:
            self.in_thinking = False
            return f"\n  {FROST_DARK}╰{'─' * 46} (interrupted) ─╯{RESET}\n\n"
        return ""


class FenceProsePainter:
    """Color prose (outside fences) with FROST_WHITE; leave fence bodies raw."""

    def __init__(self):
        self.in_fence = False
        self.tick_len = 0
        self.tick_char = "`"
        self.hold = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.hold += chunk
        parts = []
        while True:
            nl = self.hold.find("\n")
            if nl == -1:
                break
            line = self.hold[: nl + 1]
            self.hold = self.hold[nl + 1 :]
            parts.append(self._handle_line(line))
        if self.hold and not self._maybe_incomplete_opener(self.hold):
            parts.append(self._paint_body(self.hold))
            self.hold = ""
        return "".join(parts)

    def flush(self) -> str:
        if not self.hold:
            return ""
        out = self._handle_line(self.hold)
        self.hold = ""
        return out

    def _maybe_incomplete_opener(self, s: str) -> bool:
        if self.in_fence:
            return False
        stripped = s.lstrip(" \t")
        return stripped.startswith("`") or stripped.startswith("~")

    def _paint_body(self, text: str) -> str:
        if not text:
            return ""
        if self.in_fence:
            return text
        return f"{FROST_WHITE}{text}{RESET}"

    def _handle_line(self, line: str) -> str:
        parsed = _parse_fence_line(line)
        if parsed:
            tlen, tchar, info = parsed
            if not self.in_fence:
                self.in_fence = True
                self.tick_len = tlen
                self.tick_char = tchar
                return line
            if tchar == self.tick_char and tlen >= self.tick_len and not info:
                self.in_fence = False
                return line
            return line
        return self._paint_body(line)


class FenceProsePainter:

    """Color prose (outside fences) with FROST_WHITE; leave fence bodies raw."""

    def __init__(self):
        self.in_fence = False
        self.tick_len = 0
        self.tick_char = "`"
        self.hold = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.hold += chunk
        parts = []
        while True:
            nl = self.hold.find("\n")
            if nl == -1:
                break
            line = self.hold[: nl + 1]
            self.hold = self.hold[nl + 1 :]
            parts.append(self._handle_line(line))
        if self.hold and not self._maybe_incomplete_opener(self.hold):
            parts.append(self._paint_body(self.hold))
            self.hold = ""
        return "".join(parts)

    def flush(self) -> str:
        if not self.hold:
            return ""
        out = self._handle_line(self.hold)
        self.hold = ""
        return out

    def _maybe_incomplete_opener(self, s: str) -> bool:
        if self.in_fence:
            return False
        stripped = s.lstrip(" \t")
        return stripped.startswith("`") or stripped.startswith("~")

    def _paint_body(self, text: str) -> str:
        if not text:
            return ""
        if self.in_fence:
            return text
        return f"{FROST_WHITE}{text}{RESET}"

    def _handle_line(self, line: str) -> str:
        parsed = _parse_fence_line(line)
        if parsed:
            tlen, tchar, info = parsed
            if not self.in_fence:
                self.in_fence = True
                self.tick_len = tlen
                self.tick_char = tchar
                return line
            if tchar == self.tick_char and tlen >= self.tick_len and not info:
                self.in_fence = False
                return line
            return line
        return self._paint_body(line)
