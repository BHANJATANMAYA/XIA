"""
tools/registry.py — Tool Registry
"""

from typing import Dict, List, Optional, Tuple, Any

from agent.base import ToolCall, ToolResult
from tools.base import BaseTool
from core.logger import get_logger

log = get_logger(__name__)

# Map common action names to (tool_name, default_input) tuples
# This handles cases where LLM generates "write" instead of "filesystem" with action "write"
ACTION_TO_TOOL_MAP: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "write": ("filesystem", {"action": "write"}),
    "read": ("filesystem", {"action": "read"}),
    "create": ("filesystem", {"action": "write"}),
    "delete": ("filesystem", {"action": "delete"}),
    "remove": ("filesystem", {"action": "delete"}),
    "list": ("filesystem", {"action": "list"}),
    "ls": ("filesystem", {"action": "list"}),
    "mkdir": ("filesystem", {"action": "mkdir"}),
    "makedir": ("filesystem", {"action": "mkdir"}),
    "exists": ("filesystem", {"action": "exists"}),
    "info": ("filesystem", {"action": "info"}),
    "run": ("terminal", {}),
    "execute": ("terminal", {}),
    "exec": ("terminal", {}),
    "shell": ("terminal", {}),
    "terminal": ("terminal", {}),
    "search": ("search", {}),
    "find": ("search", {}),
    "browse": ("browser", {}),
    "open": ("browser", {}),
    "fetch": ("fetch", {}),
    "get": ("fetch", {}),
    "download": ("fetch", {}),
}


def _normalize_tool_name(name: str) -> str:
    return name.lower().replace("_", "").replace("-", "").replace(" ", "")


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._normalized_tools: Dict[str, str] = {}

    def register(self, tool: BaseTool):
        if not tool.enabled:
            log.info("Tool '%s' disabled — skipping", tool.name)
            return

        self._tools[tool.name] = tool
        self._normalized_tools[_normalize_tool_name(tool.name)] = tool.name
        log.info("Tool registered: %s", tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        return list(self._tools.keys())

    def describe_all(self) -> List[str]:
        return [f"{t.name}: {t.description}" for t in self._tools.values()]

    def schemas_as_prompt(self) -> str:
        if not self._tools:
            return "No tools available."
        return "\n\n".join(t.schema().to_prompt_str() for t in self._tools.values())

    def execute(self, tool_call: ToolCall) -> ToolResult:
        # Check if this is an action-based tool call (e.g., "write" -> "filesystem" with action "write")
        if tool_call.name in ACTION_TO_TOOL_MAP:
            tool_name, default_input = ACTION_TO_TOOL_MAP[tool_call.name]
            merged_input = {**default_input, **tool_call.input}
            tool_call = ToolCall(name=tool_name, input=merged_input)
            log.info("Mapped action '%s' to tool '%s' with input: %s", 
                     tool_call.name, tool_name, str(merged_input)[:120])

        tool = self._tools.get(tool_call.name)

        if tool is None:
            fuzzy = self._fuzzy_match(tool_call.name)
            if fuzzy:
                log.warning("Fuzzy match: '%s' -> '%s'", tool_call.name, fuzzy)
                tool = self._tools[fuzzy]
            else:
                available = ", ".join(self._tools.keys()) or "none"
                return ToolResult(
                    tool_name=tool_call.name,
                    output="",
                    success=False,
                    error=f"Tool '{tool_call.name}' not found. Available: {available}",
                )

        log.info("Executing tool: %s input=%s", tool.name, str(tool_call.input)[:120])
        base_result = tool.safe_execute(**tool_call.input)

        return ToolResult(
            tool_name=base_result.tool_name,
            output=base_result.output,
            success=base_result.success,
            error=base_result.error,
        )

    def _fuzzy_match(self, name: str) -> Optional[str]:
        normalized = _normalize_tool_name(name)
        exact = self._normalized_tools.get(normalized)
        if exact:
            return exact

        for normalized_registered, original_name in self._normalized_tools.items():
            if normalized in normalized_registered or normalized_registered in normalized:
                return original_name
        return None

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={list(self._tools.keys())})"


def build_default_registry(llm=None) -> "ToolRegistry":
    """Build the default tool registry with all enabled tools."""
    from tools.filesystem import FilesystemTool
    from tools.terminal import TerminalTool
    from tools.search import SearchTool
    from tools.fetch import FetchTool
    from tools.browser import BrowserTool
    from core.config import cfg

    registry = ToolRegistry()

    if cfg.tools.filesystem.enabled:
        registry.register(FilesystemTool())

    if cfg.tools.terminal.enabled:
        registry.register(TerminalTool())

    registry.register(SearchTool())
    registry.register(FetchTool())
    registry.register(BrowserTool(headless=False))

    log.info("Tool registry built: %s", registry.list_names())
    return registry

