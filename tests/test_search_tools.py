import os

from tools.search_tools import FileSearchTool, SymbolSearchTool


def test_file_search_finds_matching_files(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "alpha.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "beta.txt").write_text("hello\n", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "gamma.py").write_text("x = 1\n", encoding="utf-8")

    tool = FileSearchTool()
    result = tool.execute({"root_path": str(root), "pattern": "**/*.py"})

    assert result.success is True
    matches = result.output
    assert len(matches) == 2
    assert all(os.path.splitext(os.path.basename(path))[1] == ".py" for path in matches)


def test_symbol_search_reports_symbol_hits(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    file_path = root / "demo.py"
    file_path.write_text(
        "def build_user():\n    return {'name': 'Ada'}\n\n"
        "class UserService:\n    def fetch(self):\n        return build_user()\n",
        encoding="utf-8",
    )

    tool = SymbolSearchTool()
    result = tool.execute({"root_path": str(root), "query": "build_user|UserService"})

    assert result.success is True
    hits = result.output
    assert any(hit["symbol"] == "build_user" for hit in hits)
    assert any(hit["symbol"] == "UserService" for hit in hits)
