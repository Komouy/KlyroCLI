"""
tests/test_ux_optimizations.py — Unit tests for UX and performance optimizations:
1. Clipboard integration & /copy extraction
2. Nordic Frost syntax highlighting
3. StreamView code block syntax highlighting toggle
4. Persistent prompt history path discovery
5. Incremental workspace file caching
"""

import os
import sys
from pathlib import Path
import tempfile
import pytest

ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import clipboard_manager
import syntax_highlighter
from stream_view import CodeBlockBuffer
import session_manager
import file_manager


# ─────────────────────────────────────────────────────────────
# 1. CLIPBOARD MANAGER TESTS
# ─────────────────────────────────────────────────────────────

def test_extract_code_blocks_multiple():
    sample = (
        "Here is the code:\n\n"
        "```python:hello.py\n"
        "def say_hello():\n"
        "    print('Hello World')\n"
        "```\n\n"
        "And another one in JS:\n"
        "```javascript\n"
        "console.log('hi');\n"
        "```\n"
    )
    blocks = clipboard_manager.extract_code_blocks(sample)
    assert len(blocks) == 2
    assert blocks[0]["lang"] == "python"
    assert blocks[0]["info"] == "python:hello.py"
    assert "def say_hello():" in blocks[0]["code"]
    assert blocks[1]["lang"] == "javascript"
    assert "console.log('hi');" in blocks[1]["code"]


def test_extract_code_blocks_empty():
    assert clipboard_manager.extract_code_blocks("") == []
    assert clipboard_manager.extract_code_blocks("Just prose without code") == []


def test_get_copy_target_auto():
    # If code exists, auto picks the latest code block
    sample = "Notes\n```python\nx = 42\n```\nDone"
    target, desc = clipboard_manager.get_copy_target(sample, mode="auto")
    assert target.strip() == "x = 42"
    assert "Blok kode python" in desc

    # If no code block, auto picks the full response
    sample_prose = "Penjelasan tanpa kode."
    target, desc = clipboard_manager.get_copy_target(sample_prose, mode="auto")
    assert target == "Penjelasan tanpa kode."
    assert "Respons AI" in desc


def test_get_copy_target_code_and_all():
    sample = "<!--ACTION:SHELL cmd=\"dir\"-->\nPenjelasan.\n```bash\nls -la\n```"
    # Mode all: strips ACTION tag
    target_all, desc_all = clipboard_manager.get_copy_target(sample, mode="all")
    assert "<!--ACTION" not in target_all
    assert "Penjelasan." in target_all
    assert "ls -la" in target_all

    # Mode code: extracts only code block
    target_code, desc_code = clipboard_manager.get_copy_target(sample, mode="code")
    assert target_code.strip() == "ls -la"
    assert "Blok kode bash" in desc_code


def test_copy_to_clipboard_empty():
    ok, msg = clipboard_manager.copy_to_clipboard("")
    assert not ok
    assert "kosong" in msg.lower()


# ─────────────────────────────────────────────────────────────
# 2. SYNTAX HIGHLIGHTER TESTS
# ─────────────────────────────────────────────────────────────

def test_syntax_highlighter_python():
    line = "def calculate(a, b): # Sum"
    hl = syntax_highlighter.highlight_line(line, lang="python")
    # Keywords should have cyan ANSI code
    assert "\033[38;2;56;189;248mdef\033[0m" in hl
    # Comments should have dark ANSI code
    assert "# Sum" in hl
    assert "\033[38;2;71;85;105m# Sum\033[0m" in hl


def test_syntax_highlighter_json():
    json_line = '  "status": "success", "count": 100, "active": true'
    hl = syntax_highlighter.highlight_line(json_line, lang="json")
    assert '"status"' in hl
    assert '"success"' in hl
    assert "100" in hl
    assert "true" in hl


def test_syntax_highlighter_plain_passthrough():
    plain = "Just normal text without highlighting"
    hl = syntax_highlighter.highlight_line(plain, lang="text")
    assert hl == plain


def test_syntax_highlighter_code_block():
    code_lines = [
        "import os\n",
        "def main():\n",
        "    return 0\n",
    ]
    hl_block = syntax_highlighter.highlight_code_block(code_lines, lang="py")
    assert len(hl_block) == 3
    assert "\033[38;2;56;189;248mimport\033[0m" in hl_block[0]
    assert "\033[38;2;56;189;248mdef\033[0m" in hl_block[1]


# ─────────────────────────────────────────────────────────────
# 3. STREAM VIEW SYNTAX HIGHLIGHT TOGGLE
# ─────────────────────────────────────────────────────────────

def test_code_block_buffer_with_syntax_highlight():
    buf = CodeBlockBuffer(live_counter=False, syntax_highlight=True)
    buf.feed("```python:test.py\n")
    buf.feed("def greet():\n")
    buf.feed("    return 'hi'\n")
    revealed = buf.feed("```\n")

    assert "test.py" in revealed
    # Contains ANSI escape code from syntax highlighter
    assert "\033[38;2;56;189;248mdef\033[0m" in revealed
    assert "'hi'" in revealed


def test_code_block_buffer_without_syntax_highlight():
    # Backward compatibility: default is plain text
    buf = CodeBlockBuffer(live_counter=False, syntax_highlight=False)
    buf.feed("```python:test.py\n")
    buf.feed("def greet():\n")
    revealed = buf.feed("```\n")

    assert "test.py" in revealed
    assert "def greet():" in revealed


# ─────────────────────────────────────────────────────────────
# 4. SESSION MANAGER LAST RESPONSE & HISTORY PATH
# ─────────────────────────────────────────────────────────────

def test_session_manager_last_response():
    session_manager.set_last_response("Test AI Response with `code`")
    assert session_manager.get_last_response() == "Test AI Response with `code`"


def test_session_manager_prompt_history_path():
    p = session_manager.get_prompt_history_file()
    assert p is not None
    assert "prompt_history" in p


# ─────────────────────────────────────────────────────────────
# 5. FILE MANAGER CACHING TESTS
# ─────────────────────────────────────────────────────────────

def test_workspace_file_cache(tmp_path):
    # Create temp workspace
    f1 = tmp_path / "app.py"
    f1.write_text("print('version 1')", encoding="utf-8")

    file_manager.clear_workspace_file_cache()
    ctx1, read1, _ = file_manager.baca_semua_file(str(tmp_path))
    assert "version 1" in ctx1
    assert "app.py" in read1

    stats1 = file_manager.get_workspace_cache_stats()
    assert stats1["cached_files_count"] >= 1

    # Second read: content should come from cache
    ctx2, read2, _ = file_manager.baca_semua_file(str(tmp_path))
    assert "version 1" in ctx2

    # Modify file: cache should update with version 2
    f1.write_text("print('version 2')", encoding="utf-8")
    ctx3, _, _ = file_manager.baca_semua_file(str(tmp_path))
    assert "version 2" in ctx3

    file_manager.clear_workspace_file_cache()
    assert file_manager.get_workspace_cache_stats()["cached_files_count"] == 0
