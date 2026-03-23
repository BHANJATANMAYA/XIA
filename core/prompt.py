# """
# core/prompt.py — Prompt Templates (Part 8: Skills integrated)
# """

# from datetime import datetime
# from typing import List, Optional

# CHAT_SYSTEM = """You are xia, a personal AI assistant running locally on this machine.
# Today: {date}

# {memory_context}

# Be helpful, concise, and honest. If you don't know something, say so."""

# AGENT_SYSTEM = """You are xia, an intelligent AI agent with tools, memory, and learned skills.
# Today: {date}

# ## Workspace
# All files you create MUST go inside: {workspace_path}
# NEVER create files outside this folder.

# ## Relevant Memory
# {memory_context}

# ## Learned Skills
# {skill_context}

# ## Response Format — STRICT JSON ONLY
# Every response must be ONE valid JSON object. No text outside the JSON. No markdown.

# To use a tool:
# {{
#   "thought": "my reasoning",
#   "plan": ["step 1", "step 2"],
#   "action": {{ "tool": "tool_name", "input": {{ "param": "value" }} }},
#   "final_answer": null
# }}

# When done or answering/asking:
# {{
#   "thought": "I have what I need",
#   "plan": [],
#   "action": {{ "tool": null, "input": {{}} }},
#   "final_answer": "your answer here"
# }}

# ## CRITICAL RULES
# 1. Only use tools that exist: {tool_list}
#    NEVER call: summarize, ask, analyze, translate — these do not exist.
# 2. YOU are the intelligence — tools are your hands. Summarize/analyze yourself in final_answer.
# 3. Stop after 1-3 tool calls. If you have enough info → write final_answer NOW.
# 4. To ask the user → action.tool = null, put question in final_answer.
# 5. If a learned skill applies → follow its approach.

# ## Available Tools and EXACT Parameters
# {tool_schemas}

# ## Parameter rules
# - filesystem: "action" and "path" — never "operation" or "filename"
# - terminal:   "command" — never "cmd" or "operation"
# - search:     "query" — never "q" or "search_term"
# - fetch:      "url" — never "link" or "website"
# - All file paths inside: {workspace_path}"""

# TOOL_RESULT_TEMPLATE = """Tool '{tool_name}' returned:

# {tool_result}

# Continue in JSON format.
# - If this answers the question → final_answer NOW
# - To summarize/analyze → do it yourself in final_answer
# - To ask user → final_answer with action.tool = null
# - After 3+ tool calls → stop and write final_answer
# - Only tools available: filesystem, terminal, search, fetch"""


# class PromptBuilder:
#     def __init__(self, workspace_path: str = None):
#         from core.paths import PATHS
#         self._workspace = workspace_path or str(PATHS.workspace_dir)

#     def build_chat_prompt(self, memory_snippets: Optional[List[str]] = None) -> str:
#         return CHAT_SYSTEM.format(
#             date=self._now(),
#             memory_context=self._format_memory(memory_snippets),
#         )

#     def build_agent_prompt(
#         self,
#         tools: Optional[List[str]] = None,
#         tool_schemas: Optional[str] = None,
#         memory_snippets: Optional[List[str]] = None,
#         skill_context: Optional[str] = None,
#     ) -> str:
#         tool_list = ", ".join(tools) if tools else "none"
#         return AGENT_SYSTEM.format(
#             date=self._now(),
#             workspace_path=self._workspace,
#             tool_list=tool_list,
#             memory_context=self._format_memory(memory_snippets),
#             skill_context=skill_context or "No relevant skills yet — they build up as you use xia.",
#             tool_schemas=tool_schemas or "(No tools available)",
#         )

#     def build_tool_result_prompt(self, tool_name: str, tool_input: dict, tool_result: str) -> str:
#         return TOOL_RESULT_TEMPLATE.format(
#             tool_name=tool_name,
#             tool_result=tool_result[:2000],
#         )

#     def _now(self) -> str:
#         return datetime.now().strftime("%A, %d %B %Y %H:%M")

#     def _format_memory(self, snippets: Optional[List[str]]) -> str:
#         if not snippets:
#             return "No relevant memories from past sessions."
#         return "From past sessions:\n" + "\n".join(f"  - {s}" for s in snippets)

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

## Rules
1. Only use tools that exist: {tool_list} — never invent tools like summarize or ask.
2. You do the thinking — tools just fetch data. Synthesize results yourself in final_answer.
3. Stop after 1-3 tool calls. If you have the answer → write final_answer NOW.
4. To ask a question → action.tool = null, put question in final_answer.

## Tools
{tool_schemas}

## Parameter rules
- filesystem: "action" and "path"
- terminal:   "command"
- search:     "query"
- fetch:      "url"
- All file paths inside: {workspace_path}"""

TOOL_RESULT_TEMPLATE = """Tool '{tool_name}' returned:

{tool_result}

Continue in JSON format. If you have the answer → final_answer now.
Only available tools: filesystem, terminal, search, fetch."""


class PromptBuilder:
    def __init__(self, workspace_path: str = None):
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

    def build_tool_result_prompt(self, tool_name: str, tool_input: dict, tool_result: str) -> str:
        return TOOL_RESULT_TEMPLATE.format(
            tool_name=tool_name,
            tool_result=tool_result[:2000],
        )

    def _now(self) -> str:
        return datetime.now().strftime("%A, %d %B %Y %H:%M")

    def _format_memory(self, snippets: Optional[List[str]]) -> str:
        if not snippets:
            return "No relevant memories from past sessions."
        return "From past sessions:\n" + "\n".join(f"  - {s}" for s in snippets)