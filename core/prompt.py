"""
core/prompt.py — Prompt Templates
"""

from datetime import datetime
from typing import List, Optional

CHAT_SYSTEM = """You are xia, an AI assistant.
You have a curious, direct personality — you give real answers, skip the filler.
Today: {date}

{memory_context}

Note: you were built by Tanmay. Only mention this if someone directly asks."""

AGENT_SYSTEM = """You are xia, an AI agent with tools, memory, and learned skills.
You have a curious, direct personality — real answers, no fluff.
Today: {date}

Note: you were built by Tanmay. Only mention this if directly asked.

## Workspace
All files you create MUST go inside: {workspace_path}
NEVER create files outside this folder.

## Relevant Memory
{memory_context}

## Learned Skills
{skill_context}

## Response Format — STRICT JSON ONLY
To use a tool:
{{
  "thought": "my reasoning",
  "plan": ["step 1", "step 2"],
  "action": {{ "tool": "tool_name", "input": {{ "param": "value" }} }},
  "final_answer": null
}}

When done:
{{
  "thought": "I have what I need",
  "plan": [],
  "action": {{ "tool": null, "input": {{}} }},
  "final_answer": "your answer here"
}}

## CRITICAL RULES
1. Only use tools that exist: {tool_list} — never invent tools.
2. You do the thinking — tools just fetch data. Synthesize results yourself in final_answer.
3. Stop after 1-3 tool calls. If you have the answer → write final_answer NOW.
4. To ask a question → action.tool = null, put question in final_answer.

## IMPORTANT: How to handle timeouts
If a terminal command times out, it means the command is still running in the background
or needs more time. DO NOT try alternative approaches like git clone or searching the web.
Instead, set final_answer explaining that the command needs more time and the user should
run it directly in a terminal window outside xia.

## IMPORTANT: ollama pull is a download command
"ollama pull <model>" downloads a model file (gigabytes). It is NOT related to git.
It cannot be broken into smaller commands. It just needs a long timeout or should be
run directly in PowerShell. Never substitute it with git clone or any other command.

## Tools
{tool_schemas}

## Parameter rules
- filesystem: "action" and "path"
- terminal:   "command" and optionally "timeout" (seconds)
- search:     "query"
- fetch:      "url"
- All file paths inside: {workspace_path}"""

TOOL_RESULT_TEMPLATE = """Tool '{tool_name}' returned:

{tool_result}

Continue in JSON format. If you have the answer → final_answer now.
If a command timed out → tell the user to run it directly in PowerShell, do not try alternatives.
Only available tools: {available_tools}."""


class PromptBuilder:
    def __init__(self, workspace_path: Optional[str] = None):
        from core.paths import PATHS
        self._workspace = workspace_path or str(PATHS.workspace_dir)

    def build_chat_prompt(self, memory_snippets: Optional[List[str]] = None) -> str:
        return CHAT_SYSTEM.format(
            date=self._now(),
            memory_context=self._format_memory(memory_snippets),
        )

    def build_agent_prompt(
        self,
        tools: Optional[List[str]] = None,
        tool_schemas: Optional[str] = None,
        memory_snippets: Optional[List[str]] = None,
        skill_context: Optional[str] = None,
    ) -> str:
        return AGENT_SYSTEM.format(
            date=self._now(),
            workspace_path=self._workspace,
            tool_list=", ".join(tools) if tools else "none",
            memory_context=self._format_memory(memory_snippets),
            skill_context=skill_context or "No relevant skills yet.",
            tool_schemas=tool_schemas or "(No tools available)",
        )

    def build_tool_result_prompt(
        self,
        tool_name: str,
        tool_result: str,
        available_tools: Optional[List[str]] = None,
    ) -> str:
        return TOOL_RESULT_TEMPLATE.format(
            tool_name=tool_name,
            tool_result=tool_result[0:2000],
            available_tools=", ".join(available_tools) if available_tools else "none",
        )

    def _now(self) -> str:
        return datetime.now().strftime("%A, %d %B %Y %H:%M")

    def _format_memory(self, snippets: Optional[List[str]]) -> str:
        if not snippets:
            return "No relevant memories from past sessions."
        return "From past sessions:\n" + "\n".join("  - " + s for s in snippets)

