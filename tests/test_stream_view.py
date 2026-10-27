"""Unit tests for CodeBlockBuffer and stream_view utilities."""
import pytest
from stream_view import CodeBlockBuffer, CommentStripper, StreamIndenter


def test_code_block_buffer_prose_passthrough():
    buf = CodeBlockBuffer()
    out1 = buf.feed("Halo dunia! ")
    out2 = buf.feed("Ini adalah teks biasa.\n")
    flush_out = buf.flush()
    assert "Halo dunia! " in out1
    assert "Ini adalah teks biasa.\n" in out2
    assert flush_out == ""


def test_code_block_buffer_hides_code_until_closed():
    buf = CodeBlockBuffer()
    # 1. Prose passes through
    p1 = buf.feed("Berikut fungsinya:\n")
    assert "Berikut fungsinya:\n" in p1

    # 2. Opening fence triggers placeholder
    f1 = buf.feed("```python:calc.py\n")
    assert "Generating python" in f1
    assert "\r" in f1

    # 3. Inside code block: buffered silently
    c1 = buf.feed("def add(a, b):\n")
    c2 = buf.feed("    return a + b\n")
    assert c1 == ""
    assert c2 == ""

    # 4. Closing fence reveals the entire styled block
    f2 = buf.feed("```\n")
    assert "calc.py" in f2
    assert "def add(a, b):" in f2
    assert "return a + b" in f2
    assert "\033[2K" in f2  # erased placeholder

    # 5. Subsequent prose passes through
    p2 = buf.feed("Selesai.\n")
    assert "Selesai.\n" in p2
    assert buf.flush() == ""


def test_code_block_buffer_partial_tokens():
    """Test token-by-token streaming across fence markers."""
    buf = CodeBlockBuffer()
    chunks = ["`", "`", "`", "js", "\n", "console", ".", "log(1)", "\n", "`", "`", "`", "\n"]
    outputs = []
    for ch in chunks:
        out = buf.feed(ch)
        if out:
            outputs.append(out)
    flush_out = buf.flush()
    if flush_out:
        outputs.append(flush_out)

    combined = "".join(outputs)
    assert "console.log(1)" in combined
    assert "js" in combined


def test_code_block_buffer_nested_fences():
    """Inner fences without named files (e.g. ```bash inside markdown) should not prematurely close."""
    buf = CodeBlockBuffer()
    feed_lines = [
        "```markdown:README.md\n",
        "# Project\n",
        "```bash\n",
        "npm install\n",
        "```\n",
        "End of guide\n",
        "```\n",
    ]
    outputs = []
    for line in feed_lines:
        out = buf.feed(line)
        if out:
            outputs.append(out)

    assert len(outputs) == 2  # 1st is placeholder, 2nd is revealed block on final ```
    revealed = outputs[1]
    assert "README.md" in revealed
    assert "npm install" in revealed
    assert "End of guide" in revealed


def test_code_block_buffer_multiple_blocks():
    """Handles multiple sequential code blocks correctly."""
    buf = CodeBlockBuffer()
    stream = [
        "First block:\n",
        "```python\n",
        "x = 1\n",
        "```\n",
        "Middle prose\n",
        "```javascript\n",
        "let y = 2;\n",
        "```\n",
        "Final prose\n",
    ]
    outputs = [buf.feed(s) for s in stream]
    combined = "".join(outputs)
    assert "x = 1" in combined
    assert "let y = 2;" in combined
    assert "Middle prose" in combined
    assert "Final prose" in combined


def test_code_block_buffer_truncated_flush():
    """If stream ends unexpectedly mid-code, flush() reveals the buffered code."""
    buf = CodeBlockBuffer()
    buf.feed("```python:partial.py\n")
    buf.feed("print('unfinished')\n")
    flushed = buf.flush()
    assert "partial.py" in flushed
    assert "print('unfinished')" in flushed
    assert "(stream truncated)" in flushed


def test_code_block_buffer_cancel():
    """cancel() should clear state and return erase ANSI sequence if placeholder was active."""
    buf = CodeBlockBuffer()
    buf.feed("```python\n")
    buf.feed("print('secret')\n")
    erase = buf.cancel()
    assert "\033[2K" in erase
    # Subsequent feed should be clean
    out = buf.feed("New prose\n")
    assert "New prose\n" in out


def test_comment_stripper_with_code_buffer_pipeline():
    """Verify CommentStripper and CodeBlockBuffer work seamlessly together."""
    stripper = CommentStripper()
    code_buf = CodeBlockBuffer()

    raw_stream = [
        "<!--ACTION:WRITE_FILE-->",
        "```python:main.py\n",
        "print('clean')\n",
        "```\n",
    ]
    revealed = []
    for chunk in raw_stream:
        stripped = stripper.feed(chunk)
        visible = code_buf.feed(stripped)
        if visible:
            revealed.append(visible)

    combined = "".join(revealed)
    assert "<!--ACTION" not in combined
    assert "print('clean')" in combined


def test_code_block_buffer_live_counter():
    """Verify live shimmer wave and line counting when live_counter=True."""
    buf = CodeBlockBuffer(live_counter=True)
    open_out = buf.feed("```python:app.py\n")
    # shimmer band recolors each visible char — assert on ANSI-stripped text
    from theme import strip_ansi
    visible_open = strip_ansi(open_out)
    assert "Generating" in visible_open
    assert "python" in visible_open
    assert "[0 lines]" in visible_open

    line1_out = buf.feed("import os\n")
    assert "[1 lines]" in line1_out
    assert "\033[K" in line1_out

    line2_out = buf.feed("print('hi')\n")
    assert "[2 lines]" in line2_out

    close_out = buf.feed("```\n")
    assert "\033[2K" in close_out  # erased placeholder/counter
    assert "app.py" in close_out
    assert "import os" in close_out
    assert "print('hi')" in close_out


def test_stream_indenter_margin():
    """Verify that every line starts with clean 2 spaces margin."""
    ind = StreamIndenter(indent="  ")
    out = ind.feed("Baris pertama\nBaris kedua\n") + ind.flush()
    lines = out.splitlines()
    assert lines[0].startswith("  Baris pertama")
    assert lines[1].startswith("  Baris kedua")


def test_stream_indenter_word_wrap():
    """Verify prose word-wrapping without slicing words across terminal columns."""
    ind = StreamIndenter(indent="  ", max_cols=30)
    text = "Sistem kecerdasan buatan otonom untuk rekayasa perangkat lunak modern."
    out = ind.feed(text) + ind.flush()
    lines = out.splitlines()
    assert len(lines) > 1
    for line in lines:
        assert line.startswith("  ")
        assert len(line) <= 35  # within margin limit
    # Whole words are preserved, not split
    assert "kecerdasan" in out
    assert "perangkat" in out


def test_stream_indenter_bullet_continuation():
    """Verify continuation lines of bullets align under the bullet content."""
    ind = StreamIndenter(indent="  ", max_cols=30)
    bullet_text = "- Baca/tulis file konfigurasi utama dari direktori proyek.\n"
    out = ind.feed(bullet_text) + ind.flush()
    lines = out.splitlines()
    assert lines[0].startswith("  - Baca/tulis")
    assert lines[1].startswith("    ")  # 4 spaces indentation matching bullet


def test_stream_indenter_tab_normalization():
    """Verify tabs are normalized to 2 spaces."""
    ind = StreamIndenter(indent="  ")
    out = ind.feed("item:\tvalue\n") + ind.flush()
    assert "\t" not in out
    assert "item: value" in out


def test_stream_indenter_emoji_sanitization():
    """Verify stray emojis that corrupt Windows consoles are stripped from stream."""
    ind = StreamIndenter(indent="  ")
    raw = "Hai! 👋 Saya Klyro AI\n- 📝 Baca file\n- 🗑️ Hapus file\n"
    out = ind.feed(raw) + ind.flush()
    assert "👋" not in out
    assert "📝" not in out
    assert "🗑" not in out
    assert "Hai! Saya Klyro AI" in out
    assert "Baca file" in out


def test_stream_indenter_preserves_structural_lines():
    """Verify structural lines (box frames, code fence borders) pass through intact."""
    ind = StreamIndenter(indent="  ")
    structural = "  │ Thinking line\n  ╭─ Header ─╮\n  ╰─ Footer ─╯\n"
    out = ind.feed(structural) + ind.flush()
    assert "  │ Thinking line" in out
    assert "  ╭─ Header ─╮" in out
    assert "  ╰─ Footer ─╯" in out
