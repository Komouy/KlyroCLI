"""
shell_tools.py — Shell execution tool

Tool:
  - ShellTool: Execute arbitrary shell commands with timeout
"""

import re
import os
import subprocess
from typing import Any, Dict, Optional

from core.tool_registry import Tool, ToolResult


_DANGEROUS_PATTERNS = [
    r"\brm\s+-[rRfF]+",
    r"\bdel\s+/[sfqSFQ]+",
    r"\bformat\s+[A-Za-z]:",
    r"\bshutdown\s+-[shrf]",
    r"\bmkfs\b",
    r"\btaskkill\s+/F\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+push\s+.*--force\b",
    r"(curl|wget)\s+.*\|\s*(sh|bash|powershell|cmd)\b",
    r"\bdd\s+if=.*of=",
]


def _is_dangerous_command(command: str) -> Optional[str]:
    """Return a reason when a command matches a dangerous execution pattern."""
    normalized = command.strip()
    if not normalized:
        return "Command is empty"

    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return "blocked by safety policy"

    return None


class ShellTool(Tool):
    """Execute shell command and capture output."""
    
    name = "shell"
    description = "Execute shell command and capture output/errors"
    schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (optional, default: 30)"
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (optional)"
            },
        },
        "required": ["command"]
    }
    
    def __init__(self, base_folder: Optional[str] = None):
        super().__init__()
        self.base_folder = os.path.realpath(os.path.abspath(base_folder or os.getcwd()))

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Execute shell command."""
        self.validate_args(args)

        command = args["command"]
        timeout = args.get("timeout", 30)
        requested_cwd = args.get("cwd")
        cwd = self.base_folder
        if requested_cwd:
            requested_cwd = os.path.abspath(requested_cwd)
            resolved_cwd = os.path.realpath(requested_cwd)
            try:
                within_workspace = os.path.commonpath([self.base_folder, resolved_cwd]) == self.base_folder
            except ValueError:
                within_workspace = False
            if not within_workspace:
                return ToolResult(
                    success=False,
                    output=None,
                    error="Working directory is outside the allowed workspace",
                    details=f"Requested cwd: {requested_cwd}",
                    metadata={"command": command, "cwd": requested_cwd, "blocked": True},
                )
            cwd = resolved_cwd

        import security
        is_interactive, interactive_reason = security.check_interactive_command(command)
        if is_interactive:
            return ToolResult(
                success=False,
                output=None,
                error=f"Interactive command blocked: {interactive_reason}",
                details=f"Command: {command}",
                metadata={
                    "return_code": -1,
                    "command": command,
                    "timeout": timeout,
                    "blocked": True,
                },
            )

        block_reason = _is_dangerous_command(command)
        if block_reason:
            return ToolResult(
                success=False,
                output=None,
                error=f"Command blocked: {block_reason}",
                details=f"Command: {command}",
                metadata={
                    "return_code": -1,
                    "command": command,
                    "timeout": timeout,
                    "blocked": True,
                },
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                text=True,
            )

            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"

            success = result.returncode == 0

            return ToolResult(
                success=success,
                output=output,
                error=None if success else f"Command failed with code {result.returncode}",
                metadata={
                    "return_code": result.returncode,
                    "command": command,
                    "timeout": timeout,
                    "blocked": False,
                }
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output=None,
                error=f"Command timed out after {timeout} seconds",
                details=f"Command: {command}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                details=f"Failed to execute: {command}"
            )
