"""
tool_registry.py — Generic Tool System for CoreAgent

Every tool has:
  - name: unique identifier
  - description: what it does
  - schema: JSON schema for input validation
  - execute(): run the tool

This enables:
  - Dynamic tool registration
  - Schema-based validation
  - Tool discovery
  - Extensibility (add GitTool, TestTool, etc without changing agent)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
import json


# ─────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────

class ToolError(Exception):
    """Base exception for tool execution errors."""
    def __init__(self, tool_name: str, message: str, details: Optional[str] = None):
        self.tool_name = tool_name
        self.message = message
        self.details = details
        super().__init__(f"[{tool_name}] {message}" + (f"\n{details}" if details else ""))


class ToolExecutionError(ToolError):
    """Tool executed but returned an error."""
    pass


class ToolValidationError(ToolError):
    """Input validation failed against schema."""
    pass


class ToolNotFoundError(ToolError):
    """Tool not registered in registry."""
    pass


# ─────────────────────────────────────────────────────────────
# RESULT TYPES
# ─────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Result returned by Tool.execute()."""
    success: bool
    output: Any  # main result (file content, shell output, etc)
    error: Optional[str] = None
    details: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # tool-specific metadata
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "details": self.details,
            "metadata": self.metadata or {},
        }


# ─────────────────────────────────────────────────────────────
# TOOL INTERFACE
# ─────────────────────────────────────────────────────────────

class Tool(ABC):
    """
    Abstract base class for all tools.
    
    Example:
    
        class FileReadTool(Tool):
            name = "file_read"
            description = "Read file content"
            schema = {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "start_line": {"type": "integer", "description": "Optional start line"},
                    "end_line": {"type": "integer", "description": "Optional end line"},
                },
                "required": ["path"]
            }
            
            def execute(self, args: Dict[str, Any]) -> ToolResult:
                path = args["path"]
                ...
    """
    
    name: str  # Unique identifier (e.g., "file_read")
    description: str  # Human-readable description
    schema: Dict[str, Any]  # JSON schema for input validation
    
    def __init__(self):
        if not self.name:
            raise ValueError(f"Tool {self.__class__.__name__} must define 'name'")
        if not self.description:
            raise ValueError(f"Tool {self.__class__.__name__} must define 'description'")
        if not self.schema:
            raise ValueError(f"Tool {self.__class__.__name__} must define 'schema'")
    
    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        Execute the tool with given arguments.
        
        Args:
            args: Dict matching the tool's schema
            
        Returns:
            ToolResult with success/output/error
        """
        pass
    
    def validate_args(self, args: Dict[str, Any]) -> bool:
        """
        Validate args against schema.
        Returns True if valid, raises ToolValidationError otherwise.
        """
        required = self.schema.get("required", [])
        
        # Check required fields
        for field in required:
            if field not in args:
                raise ToolValidationError(
                    self.name,
                    f"Missing required field: {field}",
                    f"Schema requires: {required}"
                )
        
        return True
    
    def __repr__(self) -> str:
        return f"Tool({self.name})"


# ─────────────────────────────────────────────────────────────
# TOOL REGISTRY
# ─────────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Central registry for all tools.
    
    Usage:
    
        registry = ToolRegistry()
        registry.register(FileReadTool())
        registry.register(FileWriteTool())
        registry.register(ShellTool())
        
        result = registry.execute("file_read", {"path": "main.py"})
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Register a tool in the registry."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
    
    def unregister(self, tool_name: str) -> None:
        """Unregister a tool from the registry."""
        if tool_name in self._tools:
            del self._tools[tool_name]
    
    def get(self, tool_name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with metadata."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "schema": tool.schema,
            }
            for tool in self._tools.values()
        ]
    
    def execute(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with given arguments.
        
        Raises:
            ToolNotFoundError: if tool not registered
            ToolValidationError: if args don't match schema
            ToolExecutionError: if tool execution fails
        """
        tool = self.get(tool_name)
        if not tool:
            raise ToolNotFoundError(
                tool_name,
                f"Tool '{tool_name}' not registered",
                f"Available tools: {list(self._tools.keys())}"
            )
        
        try:
            # Validate args
            tool.validate_args(args)
            
            # Execute
            result = tool.execute(args)
            
            return result
            
        except ToolValidationError:
            raise
        except Exception as e:
            raise ToolExecutionError(
                tool_name,
                f"Execution failed: {str(e)}",
                str(type(e).__name__)
            )
    
    def __repr__(self) -> str:
        return f"ToolRegistry({len(self._tools)} tools)"


# ─────────────────────────────────────────────────────────────
# MUTATION CLASSIFICATION (Priority 3 — Safety)
# ─────────────────────────────────────────────────────────────
#
# Single source of truth for "which tools can change something on disk
# or run a process" (as opposed to read-only tools like file_read,
# file_search, symbol_search). Both core/agent.py (to decide when to call
# the approval gate) and core/response_planner.py (to label planned
# Actions) key off this same set, so the two can never silently drift
# apart on what counts as mutating.
MUTATING_TOOL_NAMES = {"file_write", "file_delete", "mkdir", "rename", "shell"}


def is_mutating_tool(tool_name: Optional[str]) -> bool:
    """True if `tool_name` can change something on disk or run a process."""
    return tool_name in MUTATING_TOOL_NAMES
