"""
tests/test_thinking_stream.py — Unit tests for Visual Thinking Mode & Reasoning Stream Handler
"""
import pytest
import time
from stream_view import ThinkingStreamHandler, CommentStripper, CodeBlockBuffer
from commands.command_handler import handle_slash_command
from ai import AIAssistant


def test_thinking_handler_passthrough():
    """If no <think> tag is present, content passes through untouched."""
    handler = ThinkingStreamHandler()
    out = handler.feed("Halo, ini adalah jawaban normal tanpa pemikiran.")
    flushed = handler.flush()
    assert "Halo, ini adalah jawaban normal tanpa pemikiran." in out
    assert flushed == ""


def test_thinking_handler_basic_think_block():
    """Detects <think>...</think> and formats thought process card."""
    handler = ThinkingStreamHandler()
    out1 = handler.feed("Jawaban awal. <think>Menganalisis dependensi arsitektur...")
    out2 = handler.feed(" Memilih pendekatan yang paling efisien.</think> Selesai!")
    flushed = handler.flush()

    combined = out1 + out2 + flushed
    assert "Jawaban awal." in combined
    assert "Thinking Process" in combined
    assert "Menganalisis dependensi arsitektur..." in combined
    assert "Thought for" in combined
    assert "Selesai!" in combined


def test_thinking_handler_split_tags():
    """Handles opening and closing tags split across chunks."""
    handler = ThinkingStreamHandler()
    chunks = ["Teks ", "<", "th", "ink", ">", "Memeriksa logika.", "<", "/", "thi", "nk>", " Hasil."]
    outputs = [handler.feed(c) for c in chunks]
    flushed = handler.flush()

    combined = "".join(outputs) + flushed
    assert "Teks " in combined
    assert "Thinking Process" in combined
    assert "Memeriksa logika." in combined
    assert "Thought for" in combined
    assert "Hasil." in combined


def test_thinking_handler_multiline_formatting():
    """Ensures each line in thought process has the border prefix."""
    handler = ThinkingStreamHandler()
    raw = "<think>Langkah 1: Cek file.\nLangkah 2: Buat unit test.\nLangkah 3: Jalankan.</think>Output final."
    rendered = handler.feed(raw) + handler.flush()
    assert "│" in rendered
    assert "Langkah 1: Cek file." in rendered
    assert "Langkah 2: Buat unit test." in rendered
    assert "Output final." in rendered


def test_thinking_handler_cancel():
    """Interrupted thinking stream cleanly closes border with interrupted note."""
    handler = ThinkingStreamHandler()
    handler.feed("<think>Sedang memikirkan algoritma yang rumit...")
    canc = handler.cancel()
    assert "(interrupted)" in canc
    assert handler.in_thinking is False


def test_thinking_handler_pipeline_with_code_buffer():
    """Pipeline: CommentStripper -> ThinkingStreamHandler -> CodeBlockBuffer."""
    stripper = CommentStripper()
    thinker = ThinkingStreamHandler()
    code_buf = CodeBlockBuffer()

    stream = [
        "<!--ACTION:WRITE_FILE-->",
        "<think>Perlu membuat fungsi kalkulator di calc.py</think>",
        "Berikut kode implementasinya:\n",
        "```python:calc.py\n",
        "def add(a, b):\n",
        "    return a + b\n",
        "```\n",
    ]

    outputs = []
    for chunk in stream:
        s = stripper.feed(chunk)
        t = thinker.feed(s)
        c = code_buf.feed(t)
        if c:
            outputs.append(c)

    # Flush sequence
    s_f = stripper.flush()
    t_f = thinker.feed(s_f) if s_f else ""
    t_final = thinker.flush()
    c_f = code_buf.feed(t_f + t_final)
    last = code_buf.flush()

    for p in (c_f, last):
        if p:
            outputs.append(p)

    final_text = "".join(outputs)
    assert "<!--ACTION" not in final_text
    assert "Thinking Process" in final_text
    assert "Perlu membuat fungsi kalkulator" in final_text
    assert "Thought for" in final_text
    assert "Berikut kode implementasinya:" in final_text
    assert "calc.py" in final_text
    assert "def add(a, b):" in final_text


def test_slash_think_commands(capsys):
    """Verify /think command options (status, on, off, auto)."""
    ai = AIAssistant()

    # Status
    handle_slash_command("/think", "", ".", ai)
    out_status = capsys.readouterr().out
    assert "Visual Thinking Engine" in out_status

    # ON
    handle_slash_command("/think", "on", ".", ai)
    assert ai.thinking_enabled is True
    assert ai.force_thinking is True
    out_on = capsys.readouterr().out
    assert "Thinking Mode ON" in out_on

    # OFF
    handle_slash_command("/think", "off", ".", ai)
    assert ai.thinking_enabled is False
    assert ai.force_thinking is False
    out_off = capsys.readouterr().out
    assert "Thinking Mode OFF" in out_off

    # AUTO / RESET
    handle_slash_command("/think", "auto", ".", ai)
    assert ai.thinking_enabled is True
    assert ai.force_thinking is False
    out_auto = capsys.readouterr().out
    assert "Thinking Mode: AUTO" in out_auto
