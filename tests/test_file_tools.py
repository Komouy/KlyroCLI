import pytest

from tools.file_tools import FileReadTool


def test_file_read_rejects_symlink_escape(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("outside workspace", encoding="utf-8")
    link = workspace / "linked.txt"

    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = FileReadTool(base_folder=str(workspace)).execute({"path": "linked.txt"})

    assert result.success is False
    assert "outside the allowed folder" in result.error.lower()


def test_file_write_tool_returns_syntax_diagnostics(tmp_path):
    from tools.file_tools import FileWriteTool

    tool = FileWriteTool(base_folder=str(tmp_path))

    # 1. Clean code write
    clean_res = tool.execute({
        "path": "clean.py",
        "content": "def add(a, b):\n    return a + b\n"
    })
    assert clean_res.success is True
    assert clean_res.metadata["syntax_clean"] is True
    assert "WARNING [SYNTAX_ERROR]" not in clean_res.output

    # 2. Syntax-broken code write
    broken_res = tool.execute({
        "path": "broken.py",
        "content": "def broken(:\n    pass\n"
    })
    assert broken_res.success is True  # File is written to disk
    assert broken_res.metadata["syntax_clean"] is False
    assert "WARNING [SYNTAX_ERROR]" in broken_res.output
    assert "SyntaxError on line 1" in broken_res.output