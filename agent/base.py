"""
agent/base.py — Core Agent Data Types

All data structures shared across the agent system.
The agent loop, planner, and reasoner all speak in these types.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Step types ─────────────────────────────────────────────────────────────────

class StepType(Enum):
    THINK   = "THINK"
    PLAN    = "PLAN"
    ACT     = "ACT"
    OBSERVE = "OBSERVE"
    REASON  = "REASON"
    FINAL   = "FINAL"


class StepStatus(Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    SKIPPED  = "skipped"


# ── Individual step ────────────────────────────────────────────────────────────

@dataclass
class AgentStep:
    """One step in the agent's reasoning loop."""
    step_type:  StepType
    content:    str                        # What happened in this step
    tool_name:  Optional[str]  = None      # Tool used (if ACT step)
    tool_input: Optional[Dict] = None      # Input given to tool
    tool_result: Optional[str] = None      # Result from tool
    status:     StepStatus = StepStatus.DONE
    error:      Optional[str] = None

    def is_tool_call(self) -> bool:
        return self.tool_name is not None

    def __str__(self) -> str:
        base = f"[{self.step_type.value}] {self.content[:120]}"
        if self.tool_name:
            base += f" → tool:{self.tool_name}"
        return base


# ── Full agent task result ─────────────────────────────────────────────────────

@dataclass
class AgentResult:
    """
    The complete result of running the agent on a task.
    Contains the final answer plus the full reasoning trace.
    """
    task:         str
    final_answer: str
    steps:        List[AgentStep] = field(default_factory=list)
    success:      bool = True
    error:        Optional[str] = None
    total_steps:  int = 0
    tools_used:   List[str] = field(default_factory=list)

    def thinking_trace(self) -> str:
        """Return the full reasoning trace as a readable string."""
        lines = []
        for i, step in enumerate(self.steps, 1):
            lines.append(f"Step {i} [{step.step_type.value}]")
            lines.append(f"  {step.content}")
            if step.tool_name:
                lines.append(f"  Tool: {step.tool_name}")
                lines.append(f"  Input: {step.tool_input}")
                lines.append(f"  Result: {str(step.tool_result)[:200]}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.final_answer


# ── Tool call request/response ─────────────────────────────────────────────────

@dataclass
class ToolCall:
    """A request to execute a tool."""
    name:  str
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """The result of executing a tool."""
    tool_name: str
    output:    str
    success:   bool = True
    error:     Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"[Tool Error] {self.error}"


# ── LLM decision (what the model returns each loop iteration) ─────────────────

@dataclass
class AgentDecision:
    """
    Parsed response from the LLM during the agent loop.
    The model returns JSON; this is the parsed version.
    """
    thought:      str
    plan:         List[str]            = field(default_factory=list)
    tool_call:    Optional[ToolCall]   = None
    final_answer: Optional[str]        = None

    @property
    def has_tool_call(self) -> bool:
        return self.tool_call is not None and self.tool_call.name not in {None, "null", "none", ""}

    @property
    def is_done(self) -> bool:
        if self.final_answer is None:
            return False
        # Guard against model returning a list instead of string
        if isinstance(self.final_answer, list):
            self.final_answer = " ".join(str(x) for x in self.final_answer)
        return str(self.final_answer).strip() != ""

    @classmethod
    def from_dict(cls, data: dict) -> "AgentDecision":
        """Parse the JSON dict returned by the LLM into an AgentDecision."""
        tool_call = None
        action = data.get("action", {})
        if action and action.get("tool") not in {None, "null", "none", ""}:
            tool_call = ToolCall(
                name=action["tool"],
                input=action.get("input", {}),
            )

        # Coerce final_answer to string — model sometimes returns a list
        raw_answer = data.get("final_answer")
        if isinstance(raw_answer, list):
            raw_answer = " ".join(str(x) for x in raw_answer)
        elif raw_answer is not None:
            raw_answer = str(raw_answer) if raw_answer else None

        return cls(
            thought=data.get("thought", ""),
            plan=data.get("plan", []),
            tool_call=tool_call,
            final_answer=raw_answer or None,
        )

    @classmethod
    def error_decision(cls, reason: str) -> "AgentDecision":
        """Create a fallback decision when parsing fails."""
        return cls(
            thought=f"Failed to parse LLM response: {reason}",
            final_answer=f"I encountered an error while reasoning: {reason}",
        )
