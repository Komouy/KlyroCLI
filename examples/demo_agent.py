"""
demo_agent.py — Demo: CoreAgent + ToolRegistry in action

This shows how the new architecture works:

1. Create ToolRegistry
2. Register tools
3. Create Agent with custom planner
4. Run a task
5. Observe results
"""

import sys
import os

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.agent import Agent, Action, ActionType, State
from core.tool_registry import ToolRegistry
from tools.file_tools import FileReadTool, FileWriteTool, FileDeleteTool
from tools.search_tools import FileSearchTool, SymbolSearchTool
from tools.shell_tools import ShellTool


def demo_planner(state: State):
    """
    Custom planner for demo: read main.py, then show it.
    
    This is a simple example. Real planner would use LLM.
    """
    if len(state.results) == 0:
        # First action: read ai.py
        return [
            Action(
                type=ActionType.TOOL_CALL,
                tool_name="file_read",
                args={"path": "ai.py", "start_line": 1, "end_line": 50},
                description="Read first 50 lines of ai.py"
            )
        ]
    elif len(state.results) == 1 and state.results[0].success:
        # Second action: list files in current dir (Windows-compatible)
        return [
            Action(
                type=ActionType.TOOL_CALL,
                tool_name="shell",
                args={"command": "dir"},
                description="List current directory"
            )
        ]
    
    # No more actions
    return []


def on_action_callback(action: Action):
    """Called when an action is planned."""
    print(f"\n[AGENT] Planning action: {action.description or action}")


def on_result_callback(result):
    """Called when an action completes."""
    if result.success:
        output_preview = str(result.output)[:200]
        print(f"[AGENT] ✓ Success")
        print(f"        Output: {output_preview}...")
    else:
        print(f"[AGENT] ✗ Failed: {result.error}")


def main():
    print("=" * 60)
    print("KlyroCLI v2 — CoreAgent + ToolRegistry Demo")
    print("=" * 60)
    
    # 1. Create tool registry
    print("\n[SETUP] Creating ToolRegistry...")
    registry = ToolRegistry()
    
    # 2. Register tools
    print("[SETUP] Registering tools...")
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileDeleteTool())
    registry.register(FileSearchTool())
    registry.register(SymbolSearchTool())
    registry.register(ShellTool())
    
    print(f"[SETUP] Registered {len(registry.list_tools())} tools:")
    for tool_info in registry.list_tools():
        print(f"         - {tool_info['name']}: {tool_info['description']}")
    
    # 3. Create agent
    print("\n[SETUP] Creating Agent with custom planner...")
    agent = Agent(
        tool_registry=registry,
        planner=demo_planner,
        on_action=on_action_callback,
        on_result=on_result_callback,
    )
    
    # 4. Run task
    print("\n[AGENT] Running task: 'Explore project structure'")
    print("-" * 60)
    
    state = agent.run("Explore project structure", max_steps=5)
    
    # 5. Show results
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Task: {state.task}")
    print(f"Success: {state.success}")
    print(f"Steps taken: {len(state.results)}")
    
    for i, result in enumerate(state.results, 1):
        print(f"\nStep {i}: {result.action.tool_name}")
        print(f"  Description: {result.action.description}")
        print(f"  Success: {result.success}")
        if not result.success:
            print(f"  Error: {result.error}")
        else:
            output_preview = str(result.output)[:150].replace("\n", "\n  ")
            print(f"  Output: {output_preview}...")


if __name__ == "__main__":
    main()
