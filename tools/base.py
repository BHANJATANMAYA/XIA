"""
tools/base.py — Base Tool Class

Every tool in xia inherits from BaseTool.
Defines the interface the agent uses to call any tool uniformly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolParam:
    """Describes one parameter a tool accepts."""
    name:        str
    type:        str             # "string", "integer", "boolean", "object"
    description: str
    required:    bool = True
    default:     Any  = None


@dataclass
class ToolSchema:
    """Full schema for a tool — used to build the agent's system prompt."""
    name:        str
    description: str
    params:      List[ToolParam] = field(default_factory=list)

    def to_prompt_str(self) -> str:
        """Render as a readable string for injection into the system prompt."""
        lines = [f"Tool: {self.name}", f"  {self.description}"]
        if self.params:
            lines.append("  Parameters:")
            for p in self.params:
                req = "required" if p.required else f"optional, default={p.default}"
                lines.append(f"    - {p.name} ({p.type}, {req}): {p.description}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                p.name: {
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in self.params
            },
        }


@dataclass
class ToolResult:
    """Result returned by any tool execution."""
    tool_name: str
    output:    str
    success:   bool = True
    error:     Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"[Error from {self.tool_name}]: {self.error}"


class BaseTool(ABC):
    """
    Base class for all xia tools.

    To create a new tool:
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something useful"

            def schema(self) -> ToolSchema: ...
            def execute(self, **kwargs) -> ToolResult: ...
    """

    name:        str = ""
    description: str = ""
    enabled:     bool = True

    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool's parameter schema."""
        ...

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with the given parameters.
        Must return a ToolResult — never raise exceptions.
        """
        ...

    def safe_execute(self, **kwargs) -> ToolResult:
        """
        Wrapper around execute() that catches all exceptions.
        The agent always calls this, never execute() directly.
        """
        try:
            return self.execute(**kwargs)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                output="",
                success=False,
                error=f"Unhandled exception in {self.name}: {e}",
            )

    def _ok(self, output: str) -> ToolResult:
        return ToolResult(tool_name=self.name, output=output, success=True)

    def _err(self, error: str) -> ToolResult:
        return ToolResult(tool_name=self.name, output="", success=False, error=error)
