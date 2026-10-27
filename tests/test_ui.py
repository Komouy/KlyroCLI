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
    # New: card lines close the right border for a full-frame look
    assert "╮" in out and "╯" in out
    assert out.count("│") >= 2, "card body rows should be closed with a right border"
    # New: semantic ops render with bold action glyph
    buf = io.StringIO()
    with redirect_stdout(buf):
        UI.file_created("src/new.py")
    assert "✦" in buf.getvalue()

    print("✅ All UI Abstraction Layer unit tests passed!")


def test_minimalist_theme():
    """Verify minimalist UI components: clean top bar, route badge, micro-metrics, and help."""
    from klyro_cli import render_top_bar, render_route_badge, render_micro_metrics
    from commands.command_handler import handle_slash_command

    class MockAI:
        provider = "groq"
        current_model = "llama-3.3-70b-versatile"
        auto_route = False
        _user_locked_provider = True
        last_route_reason = "[Fast Code Tier] groq"
        routing_trail = []

    # 1. Top bar: minimalist dot separators, no bulky ── dashes
    top_bar = render_top_bar(".", MockAI())
    assert "·" in top_bar
    assert "──" not in top_bar
    assert "Groq" in top_bar

    # 2. Route badge: clean brackets [Groq:model · reason]
    badge = render_route_badge(MockAI())
    assert "[" in badge and "]" in badge
    assert "Groq LPU:llama-3.3-70b-versatile" in badge

    # 3. Micro metrics: muted text, no old gradient ribbon ▰▰▰▰
    buf = io.StringIO()
    with redirect_stdout(buf):
        render_micro_metrics(1.2, "sample response" * 50, MockAI())
    metrics = buf.getvalue()
    assert "▰" not in metrics
    assert "tok/s" in metrics
    assert "Groq LPU:llama-3.3-70b-versatile" in metrics

    # 4. Help: clean 2-column layout, no unicode box borders ╭─
    buf = io.StringIO()
    with redirect_stdout(buf):
        handle_slash_command("/help", "", ".", MockAI())
    help_out = buf.getvalue()
    assert "Klyro Commands" in help_out
    assert "AI & Engine" in help_out
    assert "╭─" not in help_out
    assert "╰─" not in help_out


if __name__ == "__main__":
    test_ui_components()
    test_minimalist_theme()
