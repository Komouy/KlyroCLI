"""
test_ui_overlap.py — Terminal-grid regression tests for UI overlap bugs.

Replays the exact ANSI byte stream emitted by the banner / interactive menu
into a simulated terminal grid (cursor addressing, erase, wrap-free rows) and
asserts that no element is drawn twice and no redraw leaves residue behind.

Guards against regressions of the aurora-sweep off-by-one and the idle
shimmer tick cursor drift that caused duplicated pills/borders over content.
"""

import os
import re
import sys
import types
import shutil
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

W, H = 130, 60
_SEQ = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")


class Term:
    """Minimal ANSI terminal emulator: grid + cursor (F/B/K/CR/LF only)."""

    def __init__(self):
        self.grid = [[" "] * W for _ in range(H)]
        self.row = 0
        self.col = 0

    def feed(self, data: str):
        i, n = 0, len(data)
        while i < n:
            ch = data[i]
            if ch == "\x1b":
                m = _SEQ.match(data, i)
                if m:
                    code = m.group(2)
                    if code == "m":  # SGR (colors) — no cursor effect
                        i = m.end()
                        continue
                    arg = int(m.group(1) or 1)
                    if code in ("F", "E"):
                        self.row = max(0, self.row - arg)
                        self.col = 0
                    elif code == "B":
                        self.row = min(H - 1, self.row + arg)
                    elif code == "A":
                        self.row = max(0, self.row - arg)
                    elif code == "K":
                        p = m.group(1) or "0"
                        rng = range(self.col, W) if p == "0" else range(W)
                        for c in rng:
                            self.grid[self.row][c] = " "
                    i = m.end()
                    continue
                m2 = re.match(r"\x1b\[\?[0-9;]*[hl]", data[i:])  # private modes (?25h/l)
                if m2:
                    i += m2.end()
                    continue
                i += 1
                continue
            if ch == "\n":
                self.row = min(H - 1, self.row + 1)
                self.col = 0
            elif ch == "\r":
                self.col = 0
            else:
                if self.col < W:
                    self.grid[self.row][self.col] = ch
                self.col = min(W, self.col + 1)
            i += 1

    def rows(self):
        return ["".join(r).rstrip() for r in self.grid]


def _replay(writer) -> Term:
    buf = StringIO()
    real = sys.stdout
    sys.stdout = buf
    try:
        writer()
    finally:
        sys.stdout = real
    t = Term()
    t.feed(buf.getvalue())
    return t


def test_banner_aurora_sweep_draws_single_card(monkeypatch):
    """The aurora sweep must repaint the card exactly in place — no duplicated
    borders/pills, no struct lines smeared over content rows."""
    monkeypatch.setenv("COLUMNS", "100")  # deterministic terminal width

    import provider_manager, file_manager
    import cli.spinner as sp

    monkeypatch.setattr(provider_manager, "get_api_key", lambda p: "stub-key")
    monkeypatch.setattr(file_manager, "list_daftar_file", lambda p: ["a.py", "b.py", "c.py"])
    monkeypatch.setattr(sp, "get_git_branch", lambda p: "main")

    class StubAI:
        provider = "openrouter"
        current_model = "openrouter/free"

    t = _replay(lambda: sp.print_banner(".", StubAI()))
    rows = t.rows()

    assert sum(1 for l in rows if l.strip().startswith("╭")) == 1, "duplicated top border"
    assert sum(1 for l in rows if l.strip().startswith("╰")) == 1, "duplicated bottom border"
    for pill in ("WORKSPACE", "AI ENGINE", "QUICK START"):
        hits = [l for l in rows if pill in l]
        assert len(hits) == 1, f"{pill} drawn {len(hits)} times: {hits}"
    for l in rows:  # content rows must never be smeared by section pills
        if any(k in l for k in ("folder", "files ", "git ")):
            assert "WORKSPACE" not in l and "AI ENGINE" not in l, f"smeared: {l}"
        if any(k in l for k in ("provider", "model ", "runtime")):
            assert "QUICK START" not in l and "AI ENGINE" not in l, f"smeared: {l}"


def test_menu_shimmer_and_glide_leave_no_residue(monkeypatch):
    """Idle shimmer ticks, glide transitions and Esc must restore the cursor
    so the menu erases completely — nothing may remain on the grid."""
    monkeypatch.setenv("COLUMNS", "100")

    import cli.interactive_menu as im

    class ScriptedMSVCRT:
        """Idle polls return False until the poll budget elapses, then the
        next scripted key becomes ready. Arrow keys are two getch calls
        (prefix + key byte) like real msvcrt."""

        def __init__(self, keys, idle_polls=40):
            self.keys = list(keys)
            self.idle_polls = idle_polls
            self.count = 0

        def kbhit(self):
            self.count += 1
            return self.count > self.idle_polls

        def getch(self):
            self.count = 0
            return self.keys.pop(0) if self.keys else b"\x1b"

    fake = types.ModuleType("msvcrt")
    fk = ScriptedMSVCRT([b"\xe0", b"P", b"\x1b"])  # ArrowDown (2 bytes), then Esc
    fake.kbhit = fk.kbhit
    fake.getch = fk.getch
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(sys, "platform", "win32")

    t = _replay(lambda: im.interactive_select(
        "Select AI Provider",
        [
            {"label": "Groq LPU", "description": "configured | Ultra Fast ~500 tok/…"},
            {"label": "Cerebras", "description": "configured | Super Fast Cerebras"},
            {"label": "OpenRouter", "description": "configured | Dynamic Model Disco…"},
        ],
    ))
    rows = t.rows()
    residue = [l for l in rows if l.strip() and ("╭" in l or "Groq LPU" in l or "Cerebras" in l)]
    assert not residue, f"menu left residue after esc/glide: {residue}"
    assert any("Selection cancelled" in l for l in rows)
