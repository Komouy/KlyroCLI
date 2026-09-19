"""
test_ui.py — Unit Tests for the UI Abstraction Layer (ConsoleUI)
Verifies that the UI methods run and render outputs without raising exceptions.
"""

import os
import sys
import io
from contextlib import redirect_stdout

# Ensure project modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from theme import UI, RESET, BOLD, FROST_MINT, FROST_CORAL

def test_ui_components():
    print("🧪 Running UI Abstraction Layer unit tests...")

    # Test success rendering
    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.success("Task completed successfully!")
    out = buf.getvalue()
    assert "✓" in out
    assert "Task completed successfully!" in out

    # Test error rendering
    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.error("A critical error occurred")
    out = buf.getvalue()
    assert "✗" in out
    assert "A critical error occurred" in out

    # Test warning rendering
    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.warning("Low disk space")
    out = buf.getvalue()
    assert "⚠️" in out
    assert "Low disk space" in out

    # Test file semantic operations
    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.file_created("src/auth.py")
    out = buf.getvalue()
    assert "✦" in out
    assert "Created" in out
    assert "src/auth.py" in out

    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.file_updated("src/utils.py")
    out = buf.getvalue()
    assert "✦" in out
    assert "Updated" in out
    assert "src/utils.py" in out

    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.file_deleted("temp.py")
    out = buf.getvalue()
    assert "✦" in out
    assert "Deleted" in out
    assert "temp.py" in out

    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.folder_created("src/components")
    out = buf.getvalue()
    assert "✦" in out
    assert "Created directory" in out
    assert "src/components" in out

    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.file_renamed("old.py", "new.py")
    out = buf.getvalue()
    assert "✦" in out
    assert "Renamed" in out
    assert "old.py" in out
    assert "new.py" in out

    # Test syntax warning
    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.syntax_warning("main.py", "Unexpected EOF")
    out = buf.getvalue()
    assert "Syntax:" in out
    assert "Unexpected EOF" in out

    # Test card / box rendering
    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.card_start("Diff Analysis", "+5 -2", box_width=40)
        UI.card_line("line of text", "+", FROST_MINT, box_width=40)
        UI.card_end(box_width=40)
    out = buf.getvalue()
    assert "● Diff Analysis" in out
    assert "+5 -2" in out
    assert "line of text" in out
    assert "╭" in out
    assert "│" in out
    assert "╰" in out

    print("✅ All UI Abstraction Layer unit tests passed!")

if __name__ == "__main__":
    test_ui_components()
