from core.agent import Action, ActionType
from approval_gate import build_approval_summary


def test_build_approval_summary_for_file_write():
    action = Action(
        type=ActionType.TOOL_CALL,
        tool_name="file_write",
        args={"path": "src/app.py", "content": "print('hello')\nprint('world')\n"},
        description="Write app entry point",
    )

    summary = build_approval_summary(action, base_folder="C:/project")

    assert "Write" in summary
    assert "src/app.py" in summary
    assert "2" in summary


def test_build_approval_summary_for_shell_command():
    action = Action(
        type=ActionType.TOOL_CALL,
        tool_name="shell",
        args={"command": "echo hello"},
        description="Print a greeting",
    )

    summary = build_approval_summary(action, base_folder="C:/project")

    assert "Shell" in summary
    assert "echo hello" in summary
