"""
file_tools.py — File manipulation tools

Tools:
  - FileReadTool: Read file content with optional line range
  - FileWriteTool: Write content to file (creates if not exists)
  - FileDeleteTool: Delete a file

Sandboxing:
  Every tool here accepts an optional `base_folder` (workspace root).
  When set, all paths are resolved and checked with the SAME
  `file_manager.is_safe_path()` used by the legacy ACTION-tag pipeline in
  apply_actions.py / klyro_cli.py, instead of a re-implementation — so
  path-traversal / absolute-path escapes are rejected the same way
  everywhere. If `base_folder` isn't given, it defaults to the current
  working directory rather than being fully unrestricted, since these
  tools may be driven by AI-planned actions.
"""

import os
from typing import Any, Dict, Optional

from core.tool_registry import Tool, ToolResult

try:
    import file_manager
except ImportError:  # pragma: no cover - only if tools/ is used outside KlyroCLI's own root
    file_manager = None


def _resolve_within_base(path: str, base_folder: Optional[str]):
    """
    Resolve `path` against `base_folder` and refuse anything that escapes it
    (relative traversal like '../../etc/passwd', or an absolute path that
    points somewhere else entirely).

    Returns (abs_path, error_message). abs_path is None if rejected.
    """
    base_folder = os.path.abspath(base_folder or os.getcwd())
    target = path if os.path.isabs(path) else os.path.join(base_folder, path)
    target = os.path.abspath(target)

    if file_manager is not None:
        safe = file_manager.is_safe_path(base_folder, target, rel_path=path)
    else:
        # file_manager not importable (tools/ used standalone) - fall back to
        # an equivalent commonpath check so this is never silently skipped.
        try:
            safe = os.path.commonpath([base_folder, target]) == base_folder
        except ValueError:
            safe = False

    if not safe:
        return None, f"Access denied: '{path}' is outside the allowed folder ({base_folder})"
    return target, None


class FileReadTool(Tool):
    """Read file content, optionally from specific line range."""
    
    name = "file_read"
    description = "Read file content with optional line range (1-indexed)"
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to read (absolute or relative)"
            },
            "start_line": {
                "type": "integer",
                "description": "Start line (1-indexed, optional)"
            },
            "end_line": {
                "type": "integer",
                "description": "End line inclusive (1-indexed, optional)"
            },
        },
        "required": ["path"]
    }

    def __init__(self, base_folder: Optional[str] = None):
        super().__init__()
        self.base_folder = base_folder
    
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Read file and return content."""
        self.validate_args(args)
        
        raw_path = args["path"]
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        
        try:
            path, denied = _resolve_within_base(raw_path, self.base_folder)
            if denied:
                return ToolResult(success=False, output=None, error=denied)
            
            if not os.path.exists(path):
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"File not found: {path}"
                )
            
            if not os.path.isfile(path):
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Path is not a file: {path}"
                )
            
            # Read file
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            # Extract range if specified
            if start_line is not None or end_line is not None:
                start_idx = (start_line or 1) - 1  # Convert to 0-indexed
                end_idx = (end_line or len(lines))  # End is inclusive
                lines = lines[start_idx:end_idx]
            
            content = "".join(lines)
            
            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "path": path,
                    "lines": len(content.splitlines()),
                    "size_bytes": len(content.encode("utf-8"))
                }
            )
        
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                details=f"Failed to read {raw_path}"
            )


class FileWriteTool(Tool):
    """Write content to file. Creates file if not exists, overwrites if exists."""
    
    name = "file_write"
    description = "Write content to file (creates or overwrites)"
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to write"
            },
            "content": {
                "type": "string",
                "description": "Content to write"
            },
            "append": {
                "type": "boolean",
                "description": "Append to file instead of overwrite (optional)"
            },
        },
        "required": ["path", "content"]
    }

    def __init__(self, base_folder: Optional[str] = None):
        super().__init__()
        self.base_folder = base_folder
    
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Write content to file."""
        self.validate_args(args)
        
        raw_path = args["path"]
        content = args["content"]
        append = args.get("append", False)
        
        try:
            path, denied = _resolve_within_base(raw_path, self.base_folder)
            if denied:
                return ToolResult(success=False, output=None, error=denied)
            
            # Create directory if not exists
            dir_path = os.path.dirname(path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            
            # Write file
            mode = "a" if append else "w"
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)
            
            # Run post-edit syntax / linter diagnostics
            diag_clean = True
            diag_msg = ""
            diag_details = {}
            try:
                import validations
                diag_clean, diag_msg, diag_details = validations.run_post_edit_diagnostics(path, content)
            except Exception:
                pass

            output_msg = f"Written to {path}"
            if not diag_clean:
                output_msg += f"\nWARNING [SYNTAX_ERROR]: {diag_msg}\nPlease review and correct the syntax error."

            return ToolResult(
                success=True,
                output=output_msg,
                details=None if diag_clean else diag_msg,
                metadata={
                    "path": path,
                    "size_bytes": len(content.encode("utf-8")),
                    "append": append,
                    "syntax_clean": diag_clean,
                    "syntax_diagnostics": diag_details,
                }
            )
        
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                details=f"Failed to write {raw_path}"
            )


class FileDeleteTool(Tool):
    """Delete a file."""
    
    name = "file_delete"
    description = "Delete a file"
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to delete"
            },
        },
        "required": ["path"]
    }

    def __init__(self, base_folder: Optional[str] = None):
        super().__init__()
        self.base_folder = base_folder
    
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Delete file."""
        self.validate_args(args)
        
        raw_path = args["path"]
        
        try:
            path, denied = _resolve_within_base(raw_path, self.base_folder)
            if denied:
                return ToolResult(success=False, output=None, error=denied)
            
            if not os.path.exists(path):
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"File not found: {path}"
                )
            
            if not os.path.isfile(path):
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Path is not a file: {path}"
                )
            
            # Delete file
            os.remove(path)
            
            return ToolResult(
                success=True,
                output=f"Deleted {path}",
                metadata={"path": path}
            )
        
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                details=f"Failed to delete {raw_path}"
            )


class MkdirTool(Tool):
    """Create a directory (and any missing parent directories)."""

    name = "mkdir"
    description = "Create a directory, including parent directories if needed"
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to create"
            },
        },
        "required": ["path"]
    }

    def __init__(self, base_folder: Optional[str] = None):
        super().__init__()
        self.base_folder = base_folder

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Create directory."""
        self.validate_args(args)

        raw_path = args["path"]

        try:
            path, denied = _resolve_within_base(raw_path, self.base_folder)
            if denied:
                return ToolResult(success=False, output=None, error=denied)

            os.makedirs(path, exist_ok=True)

            return ToolResult(
                success=True,
                output=f"Created directory {path}",
                metadata={"path": path}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                details=f"Failed to create directory {raw_path}"
            )


class RenameTool(Tool):
    """Rename or move a file/directory. Both endpoints must stay inside base_folder."""

    name = "rename"
    description = "Rename or move a file/directory within the workspace"
    schema = {
        "type": "object",
        "properties": {
            "src": {
                "type": "string",
                "description": "Current path"
            },
            "dst": {
                "type": "string",
                "description": "New path"
            },
        },
        "required": ["src", "dst"]
    }

    def __init__(self, base_folder: Optional[str] = None):
        super().__init__()
        self.base_folder = base_folder

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Rename/move a file or directory."""
        self.validate_args(args)

        raw_src = args["src"]
        raw_dst = args["dst"]

        try:
            src, denied = _resolve_within_base(raw_src, self.base_folder)
            if denied:
                return ToolResult(success=False, output=None, error=denied)

            dst, denied = _resolve_within_base(raw_dst, self.base_folder)
            if denied:
                return ToolResult(success=False, output=None, error=denied)

            if not os.path.exists(src):
                return ToolResult(success=False, output=None, error=f"Source not found: {src}")

            os.rename(src, dst)

            return ToolResult(
                success=True,
                output=f"Renamed {src} -> {dst}",
                metadata={"src": src, "dst": dst}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                details=f"Failed to rename {raw_src} -> {raw_dst}"
            )
