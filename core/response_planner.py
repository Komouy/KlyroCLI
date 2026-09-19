"""
response_planner.py — Turns a raw AI response into CoreAgent Action[]

This is the bridge between "Priority 1" (CoreAgent + ToolRegistry) and the
AI response format Klyro already speaks. It intentionally does NOT invent a
new wire format for the LLM to learn — it parses the SAME two formats the
legacy pipeline (apply_actions.py + execute_ai_actions() in klyro_cli.py)
already understands:

  1. Named fenced code blocks -> file_write
         ```python:main.py
         ...
         ```
     (also "### FILE: path", and first-line "# path.py" / "// path.js" hints
     — all handled by file_manager.extract_named_file_fences, reused here
     rather than re-implemented.)

  2. HTML-comment ACTION tags -> file_delete / mkdir / rename / shell
         <!--ACTION:DELETE path="old.py" -->
         <!--ACTION:MKDIR path="src/utils" -->
         <!--ACTION:RENAME from="a.py" to="b.py" -->
         <!--ACTION:SHELL cmd="pytest" -->
     (same regex as execute_ai_actions() in klyro_cli.py, reused here.)

This module only PLANS actions - it never executes or asks for
confirmation. Wiring the resulting Action[] into a live run (via
Agent(on_action=..., on_result=...)) with an approval gate for mutating
tools is a separate, later step.
"""

import re
from typing import List

import file_manager
from core.agent import Action, ActionType
from core.tool_registry import is_mutating_tool

# Same patterns execute_ai_actions() in klyro_cli.py uses - kept identical so
# the planner and the legacy pipeline always agree on what an ACTION tag is.
_ACTION_TAG = re.compile(r'<!--\s*ACTION:(\w+)\s+(.*?)\s*-->', re.IGNORECASE)
_ACTION_ATTR = re.compile(r'(\w+)="([^"]*?)"')

# Tool names must match what's registered in tools/__init__.py
_READ_ONLY_TOOLS = {"file_search", "symbol_search", "file_read"}


def _parse_action_tags(response_text: str) -> List[Action]:
    """<!--ACTION:TYPE key="value" --> comments -> Action(TOOL_CALL, ...)."""
    actions: List[Action] = []

    for match in _ACTION_TAG.finditer(response_text):
        action_type = match.group(1).upper()
        attrs = dict(_ACTION_ATTR.findall(match.group(2)))

        if action_type == "DELETE":
            raw_paths = attrs.get("path", "")
            for rel in [p.strip() for p in raw_paths.replace(";", ",").split(",") if p.strip()]:
                actions.append(Action(
                    type=ActionType.TOOL_CALL,
                    tool_name="file_delete",
                    args={"path": rel},
                    description=f"Delete {rel}",
                ))

        elif action_type == "MKDIR":
            path_rel = attrs.get("path", "")
            if path_rel:
                actions.append(Action(
                    type=ActionType.TOOL_CALL,
                    tool_name="mkdir",
                    args={"path": path_rel},
                    description=f"Create directory {path_rel}",
                ))

        elif action_type == "RENAME":
            src = attrs.get("from", "")
            dst = attrs.get("to", "")
            if src and dst:
                actions.append(Action(
                    type=ActionType.TOOL_CALL,
                    tool_name="rename",
                    args={"src": src, "dst": dst},
                    description=f"Rename {src} -> {dst}",
                ))

        elif action_type == "SHELL":
            cmd = attrs.get("cmd", "")
            if cmd:
                actions.append(Action(
                    type=ActionType.TOOL_CALL,
                    tool_name="shell",
                    args={"command": cmd},
                    description=f"Run: {cmd}",
                ))
        # Unknown ACTION types are intentionally ignored here (same as
        # execute_ai_actions(), which only branches on known types) rather
        # than raising, since a future AI response format update shouldn't
        # crash planning - it just won't produce an Action for that tag.

    return actions


def _parse_file_writes(response_text: str) -> List[Action]:
    """Named fenced code blocks -> Action(TOOL_CALL, tool_name='file_write')."""
    actions: List[Action] = []
    for filename, body in file_manager.extract_named_file_fences(response_text).items():
        filename = filename.strip()
        if not filename:
            continue
        actions.append(Action(
            type=ActionType.TOOL_CALL,
            tool_name="file_write",
            args={"path": filename, "content": body.strip()},
            description=f"Write {filename}",
        ))
    return actions


def parse_ai_response(response_text: str) -> List[Action]:
    """
    Convert a raw AI response into an ordered list of Actions.

    File writes are planned before ACTION tags (mkdir/rename/delete/shell)
    because a SHELL command such as "pytest" often assumes the files the
    same response just wrote already exist on disk.
    """
    if not response_text:
        return []

    actions = _parse_file_writes(response_text)
    actions.extend(_parse_action_tags(response_text))
    return actions


def is_mutating(action: Action) -> bool:
    """True if this action can change something on disk / run a process.

    Delegates to tool_registry.is_mutating_tool (single source of truth,
    also used by core/agent.py's approval gate) rather than keeping a
    second copy of the tool-name set here.
    """
    return is_mutating_tool(action.tool_name)
