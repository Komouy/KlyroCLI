# CoreAgent Quick Start Guide

## What is CoreAgent?

CoreAgent is the **autonomous loop** at the heart of KlyroCLI v2. It enables true agent behavior:

```
Task: "Fix login bug"
    ↓
Agent plans: [read_auth_file, read_db_file, identify_error, edit_file, run_tests]
    ↓
Agent executes each action (with auto-retry on transient errors)
    ↓
Agent observes results and decides next step
    ↓
Done
```

---

## Basic Usage

### Step 1: Create a ToolRegistry

```python
from core.tool_registry import ToolRegistry
from tools.file_tools import FileReadTool, FileWriteTool
from tools.shell_tools import ShellTool

registry = ToolRegistry()
registry.register(FileReadTool())
registry.register(FileWriteTool())
registry.register(ShellTool())
```

### Step 2: Create a Planner

The planner decides what actions to take:

```python
from core.agent import State, Action, ActionType

def my_planner(state: State) -> list[Action]:
    """
    Decide what to do next based on current state.
    
    Args:
        state: Current agent state with:
            - state.task: Original task description
            - state.results: All previous action results
            - state.context: Task-specific data from results
    
    Returns:
        List of actions to execute, or [] if done
    """
    
    if len(state.results) == 0:
        # First step: read the main file
        return [
            Action(
                type=ActionType.TOOL_CALL,
                tool_name="file_read",
                args={"path": "main.py"},
                description="Read main.py"
            )
        ]
    
    elif len(state.results) == 1:
        # Second step: run tests
        return [
            Action(
                type=ActionType.TOOL_CALL,
                tool_name="shell",
                args={"command": "python -m pytest"},
                description="Run tests"
            )
        ]
    
    # No more actions
    return []
```

### Step 3: Create and Run Agent

```python
from core.agent import Agent

agent = Agent(tool_registry=registry, planner=my_planner)
state = agent.run("Fix login bug", max_steps=10)

# Results
print(f"Success: {state.success}")
print(f"Steps: {len(state.results)}")
for result in state.results:
    print(f"  - {result.action.tool_name}: {result.success}")
```

---

## Advanced: Custom Callbacks

```python
def on_action_planned(action):
    print(f"[PLAN] {action.description}")

def on_action_completed(result):
    if result.success:
        print(f"[OK] {result.action.tool_name}")
    else:
        print(f"[ERROR] {result.error}")

agent = Agent(
    tool_registry=registry,
    planner=my_planner,
    on_action=on_action_planned,
    on_result=on_action_completed,
)

state = agent.run("My task")
```

---

## Error Handling & Retry

CoreAgent automatically handles errors:

```
Transient error (timeout, connection)
    → Retry with exponential backoff (1s, 2s, 4s, 8s)
    
Rate limit (429, quota exceeded)
    → Backoff + try next provider (if configured)
    
Permanent error (404, invalid args, auth)
    → Fail immediately
    
Unknown error
    → Optimistic retry (treat as transient)
```

You can customize this:

```python
from core.error_handler import RetryPolicy, BackoffStrategy

backoff = BackoffStrategy(
    initial_delay=0.5,
    max_delay=16.0,
    multiplier=2.0,
    max_retries=3,
)
policy = RetryPolicy(backoff)

agent = Agent(tool_registry=registry, retry_policy=policy, planner=my_planner)
```

---

## Creating Custom Tools

A tool is just a class:

```python
from core.tool_registry import Tool, ToolResult
from typing import Dict, Any

class MyCustomTool(Tool):
    name = "my_tool"
    description = "Do something useful"
    schema = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Input parameter"
            }
        },
        "required": ["input"]
    }
    
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        try:
            input_val = args["input"]
            # Do something
            result = f"Processed: {input_val}"
            
            return ToolResult(
                success=True,
                output=result,
                metadata={"processed": True}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )

# Register it
registry.register(MyCustomTool())

# Agent can now use it!
```

---

## Typical Agent Task Loop

```python
# 1. Read files to understand context
Action(TOOL_CALL, "file_read", {"path": "auth.py"})
    ↓ Result: file content in state.context["file_read"]

# 2. Search for related files
Action(TOOL_CALL, "file_search", {"pattern": "*auth*"})
    ↓ Result: list of files in state.context["file_search"]

# 3. Read related files
Action(TOOL_CALL, "file_read", {"path": "login.py"})
    ↓ Result: file content

# 4. Run tests to identify error
Action(TOOL_CALL, "shell", {"command": "pytest -v"})
    ↓ Result: test output with error details

# 5. Edit file based on error
Action(TOOL_CALL, "file_write", {"path": "auth.py", "content": "..."})
    ↓ Result: file written

# 6. Verify fix with tests
Action(TOOL_CALL, "shell", {"command": "pytest -v"})
    ↓ Result: all tests pass

# Done!
```

---

## FAQ

**Q: How does CoreAgent decide what to do?**  
A: Via the `planner` function. You provide the logic. Later, we'll use LLM to auto-generate plans.

**Q: What if a tool fails?**  
A: Agent classifies the error:
- Transient → retry with backoff
- Permanent → stop
- Rate limit → try next provider
- Auth error → ask user

**Q: Can I combine multiple tools?**  
A: Yes! Your planner returns a list of actions, executed sequentially.

**Q: How do I add a new tool?**  
A: 
1. Create a class inheriting from Tool
2. Define name, description, schema
3. Implement execute()
4. Register: `registry.register(MyTool())`

**Q: Can I use CoreAgent with the existing klyro_cli.py?**  
A: Yes! Gradually:
1. Create registry with current tools
2. Replace AI calls with `agent.run(task)`
3. Implement LLM planner to parse AI responses
4. Migrate slash commands to Tool wrappers

---

## See Also

- `PRIORITY_1_COMPLETE.md` — Architecture details
- `demo_agent.py` — Working example
- `core/agent.py` — Full implementation
- `core/tool_registry.py` — Tool system
- `core/error_handler.py` — Error handling
