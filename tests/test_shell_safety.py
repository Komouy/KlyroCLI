from tools.shell_tools import ShellTool


def test_dangerous_shell_command_is_blocked():
    tool = ShellTool()
    result = tool.execute({"command": "rm -rf /tmp/unsafe-folder"})

    assert result.success is False
    assert "blocked by safety policy" in result.error.lower()


def test_safe_shell_command_runs():
    tool = ShellTool()
    result = tool.execute({"command": "echo hello"})

    assert result.success is True
    assert "hello" in result.output.lower()


def test_shell_cwd_outside_workspace_is_blocked(tmp_path):
    tool = ShellTool(base_folder=str(tmp_path / "workspace"))
    outside = tmp_path / "outside"
    outside.mkdir()

    result = tool.execute({"command": "echo hello", "cwd": str(outside)})

    assert result.success is False
    assert "outside the allowed workspace" in result.error.lower()


def test_interactive_shell_command_is_blocked():
    tool = ShellTool()

    # Interactive commands should fail before running
    for cmd in ["vim myfile.py", "nano config.json", "less README.md", "git commit", "python"]:
        result = tool.execute({"command": cmd})
        assert result.success is False
        assert "interactive command blocked" in result.error.lower()

    # Non-interactive variants should not be flagged as interactive
    import security
    is_interactive, _ = security.check_interactive_command('git commit -m "initial commit"')
    assert is_interactive is False

    is_interactive, _ = security.check_interactive_command('python script.py --arg 1')
    assert is_interactive is False

    is_interactive, _ = security.check_interactive_command('npm init -y')
    assert is_interactive is False

