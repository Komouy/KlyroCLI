"""
agent.py — CoreAgent: Autonomous Agent Loop

The heart of KlyroCLI v2. Orchestrates:
  1. Planning (task → actions)
  2. Execution (action → tool call)
  3. Observation (result analysis)
  4. Error handling & retry

Architecture:
    
    run(task)
         │
         ▼
    plan() → Action[]
         │
         ▼
    for each action:
        │
        ├─ execute() → Result
        │
        ├─ observe() → State
        │
        └─ if error: retry_policy()
                │
           ┌────┴────┐
           │         │
         RETRY     FAIL
           │
         back to execute()
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from .tool_registry import ToolRegistry, ToolResult, ToolError, is_mutating_tool
from .error_handler import ErrorClassifier, RetryPolicy, ErrorClass


class ActionType(Enum):
    """Types of actions the agent can plan."""
    TOOL_CALL = "tool_call"  # Call a tool
    QUERY = "query"          # Query the AI
    OBSERVE = "observe"      # Analyze current state
    DECIDE = "decide"        # Make a decision


@dataclass
class Action:
    """
    An action the agent plans to take.
    
    Example:
        Action(
            type=ActionType.TOOL_CALL,
            tool_name="file_read",
            args={"path": "main.py"},
            description="Read main.py to understand project entry point"
        )
    """
    type: ActionType
    tool_name: Optional[str] = None      # If type==TOOL_CALL
    args: Optional[Dict[str, Any]] = None  # Tool arguments
    description: Optional[str] = None   # Human-readable description
    
    def __repr__(self) -> str:
        if self.type == ActionType.TOOL_CALL:
            return f"Action(TOOL_CALL: {self.tool_name})"
        return f"Action({self.type.value})"


@dataclass
class Result:
    """Result from an action execution."""
    action: Action
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_class: Optional[ErrorClass] = None  # For retry decisions
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class State:
    """Agent's current state during task execution."""
    task: str
    actions_taken: List[Action]
    results: List[Result]
    context: Dict[str, Any]  # Task-specific context (files read, symbols found, etc)
    finished: bool = False
    success: bool = False
    final_output: Optional[Any] = None


class Agent:
    """
    Autonomous agent that can plan, execute, observe, and retry.
    
    Usage:
    
        agent = Agent(tool_registry)
        state = agent.run("Fix authentication bug in login.py")
        
        if state.success:
            print(state.final_output)
    """
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        retry_policy: Optional[RetryPolicy] = None,
        planner: Optional[Callable] = None,
        on_action: Optional[Callable[[Action], None]] = None,
        on_result: Optional[Callable[[Result], None]] = None,
        approval_callback: Optional[Callable[[Action], bool]] = None,
    ):
        """
        Args:
            tool_registry: Registry of available tools
            retry_policy: Custom retry policy (default: standard backoff)
            planner: Custom planner function (default: stub that awaits AI)
            on_action: Callback when action is planned
            on_result: Callback when action completes
            approval_callback: Gate called BEFORE executing any mutating
                tool call (file_write/file_delete/mkdir/rename/shell, per
                tool_registry.is_mutating_tool) — return False to decline
                and skip execution. Read-only tools (file_read,
                file_search, symbol_search) never go through this gate.
                Left as None means "no gate" (e.g. tests/demo_agent.py
                running headless) — core/ stays usable without a
                terminal attached; the CLI wires a real gate via
                approval_gate.make_approval_gate().
        """
        self.tools = tool_registry
        self.retry_policy = retry_policy or RetryPolicy()
        self.planner = planner or self._default_planner
        self.on_action = on_action
        self.on_result = on_result
        self.approval_callback = approval_callback
    
    def run(self, task: str, max_steps: int = 10) -> State:
        """
        Run the agent loop for a given task.
        
        Args:
            task: The task description (e.g., "Fix login bug")
            max_steps: Max number of actions before stopping
            
        Returns:
            Final state with results and output
        """
        state = State(
            task=task,
            actions_taken=[],
            results=[],
            context={},
        )
        
        step = 0
        while step < max_steps and not state.finished:
            # 1. PLAN: What should we do next?
            actions = self._plan(state)
            
            if not actions:
                # Nothing planned, we're done
                state.finished = True
                state.success = True
                break
            
            # 2. EXECUTE: Do each planned action
            for action in actions:
                if self.on_action:
                    self.on_action(action)

                # APPROVAL GATE: mutating tool calls must be confirmed
                # before they touch disk or run a process. This runs
                # BEFORE _execute() (not inside it) so a decline never
                # even reaches ToolRegistry.execute() — same principle
                # as the legacy ACTION-tag pipeline in klyro_cli.py,
                # which always asks first and only calls os.remove /
                # subprocess.run / etc. after the user confirms.
                if (
                    self.approval_callback
                    and action.type == ActionType.TOOL_CALL
                    and is_mutating_tool(action.tool_name)
                    and not self.approval_callback(action)
                ):
                    result = Result(
                        action=action,
                        success=False,
                        error="Declined by user at approval gate",
                        # error_class intentionally left None: this isn't
                        # a transient/permanent tool failure to classify
                        # for retry, it's a deliberate human decision.
                        # Leaving it None means the retry/backoff loop
                        # below is skipped entirely and the agent just
                        # moves on to the next planned action - it does
                        # not silently keep retrying something the user
                        # already said no to.
                    )
                    state.results.append(result)
                    if self.on_result:
                        self.on_result(result)
                    continue

                result = self._execute(action, state)
                state.results.append(result)
                
                if self.on_result:
                    self.on_result(result)
                
                # 3. OBSERVE: Analyze result
                self._observe(result, state)
                
                # 4. RETRY or FAIL?
                # `attempt` increments on every real retry so BackoffStrategy
                # actually ramps up (1s -> 2s -> 4s -> ... -> max_retries) and
                # should_retry() eventually returns False, instead of always
                # being asked about attempt 0 forever.
                attempt = 0
                while not result.success and result.error_class:
                    retry_action = self.retry_policy.decide(result.error_class, attempt=attempt)

                    if retry_action == "RETRY":
                        self.retry_policy.backoff.wait(attempt)
                        attempt += 1
                        result = self._execute(action, state)
                        state.results.append(result)
                        if self.on_result:
                            self.on_result(result)
                        self._observe(result, state)
                        continue

                    elif retry_action == "FALLBACK":
                        # Try next provider (for AI calls)
                        # This will be handled by AIAssistant layer
                        state.finished = True
                        state.success = False
                        break

                    elif retry_action == "FAIL":
                        state.finished = True
                        state.success = False
                        break

                    elif retry_action == "ASK_USER":
                        # e.g. invalid/missing API key - needs a human, don't
                        # keep looping silently. Previously this case wasn't
                        # handled at all and fell through unnoticed.
                        state.finished = True
                        state.success = False
                        state.context["needs_user_input"] = result.error
                        break

                    else:
                        # Unknown decision string - stop instead of spinning.
                        state.finished = True
                        state.success = False
                        break

                if state.finished:
                    break
            
            step += 1
        
        if step >= max_steps:
            state.finished = True
            state.success = False
        
        state.final_output = state.context.get("final_output", None)
        return state
    
    def _plan(self, state: State) -> List[Action]:
        """
        Plan next actions based on current state.
        
        For now: return empty (caller/AI will decide)
        Later: use LLM to decide next actions
        """
        return self.planner(state)
    
    def _execute(self, action: Action, state: State) -> Result:
        """Execute an action and return result."""
        result = Result(action=action, success=False)
        
        try:
            if action.type == ActionType.TOOL_CALL:
                tool_result = self.tools.execute(action.tool_name, action.args or {})
                result.success = tool_result.success
                result.output = tool_result.output
                result.error = tool_result.error
                result.metadata = tool_result.metadata
                if not tool_result.success:
                    # Tool returned a clean logical failure (non-zero exit
                    # code, file not found, sandbox rejection, etc.)
                    # without raising. Previously this left error_class
                    # unset, so run()'s retry/fail check never triggered -
                    # the agent silently moved on and state.success ended
                    # up True even though this action failed.
                    #
                    # Classified as PERMANENT (fail, don't auto-retry)
                    # rather than run through the full retry/backoff path:
                    # blindly re-running a failed shell command or file
                    # write could repeat a side effect instead of fixing
                    # anything. Only exceptions below get the nuanced
                    # transient/rate-limit/etc. classification, since those
                    # are the network/provider-style errors that classifier
                    # was designed for.
                    result.error_class = ErrorClass.PERMANENT
            else:
                result.error = f"Action type {action.type.value} not implemented"
        
        except ToolError as e:
            result.success = False
            result.error = str(e)
            result.error_class = ErrorClassifier.classify(e)
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.error_class = ErrorClassifier.classify(e)
        
        return result
    
    def _observe(self, result: Result, state: State) -> None:
        """
        Analyze result and update state context.
        
        For now: just store output
        Later: extract symbols, dependencies, errors, etc
        """
        if result.success:
            action_key = f"{result.action.tool_name}"
            state.context[action_key] = result.output
    
    def _default_planner(self, state: State) -> List[Action]:
        """
        Default planner: returns empty (agents should provide custom planner).
        This is intentionally a stub.
        """
        return []
