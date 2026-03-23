"""
tools/registry.py — Tool Registry
"""

from typing import Dict, List, Optional

from agent.base import ToolCall, ToolResult
from tools.base import BaseTool
from core.logger import get_logger

log = get_logger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        if not tool.enabled:
            log.info("Tool '%s' disabled — skipping", tool.name)
            return
        self._tools[tool.name] = tool
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
        tool = self._tools.get(tool_call.name)

        if tool is None:
            fuzzy = self._fuzzy_match(tool_call.name)
            if fuzzy:
                log.warning("Fuzzy match: '%s' → '%s'", tool_call.name, fuzzy)
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
        name_lower = name.lower().replace("_", "").replace("-", "").replace(" ", "")
        for registered in self._tools:
            reg_lower = registered.lower().replace("_", "").replace("-", "")
            if name_lower == reg_lower or name_lower in reg_lower or reg_lower in name_lower:
                return registered
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
    from tools.leetcode import LeetCodeTool
    from core.config import cfg

    registry = ToolRegistry()

    if cfg.tools.filesystem.enabled:
        registry.register(FilesystemTool())

    if cfg.tools.terminal.enabled:
        registry.register(TerminalTool())

    registry.register(SearchTool())
    registry.register(FetchTool())

    # Browser tool — shared instance so LeetCode reuses the same browser session
    browser = BrowserTool(headless=False)
    registry.register(browser)

    # LeetCode tool — gets the browser and LLM injected
    registry.register(LeetCodeTool(browser_tool=browser, llm=llm))

    log.info("Tool registry built: %s", registry.list_names())
    return registry
