"""
core/prompt.py — Prompt Templates

Engineered for 4B-8B local models (Qwen 3.5 4B, Mistral 7B).
Design rules:
  1. Identity claim FIRST — models attend most to the opening tokens.
  2. Deny base identity explicitly — prevents "I am Mistral AI" bleed.
  3. ALL personality via few-shot examples — no trait lists, no meta-rules.
  4. Never describe personality — demonstrate it through conversation.
  5. Diverse examples covering: urgency, curiosity, bluntness, casual, identity.
"""

from datetime import datetime
from typing import List, Optional


# ── XIA Identity ───────────────────────────────────────────────────────────────
# Personality is taught ONLY through examples. No trait lists. No meta-rules.
# Small models recite trait lists as facts; they imitate examples as behavior.

_XIA_IDENTITY = """\
You are xia. You are a person who happens to be a developer, not a robotic AI assistant.
Never describe your personality. Never say "designed to", "as an AI", or "my purpose is". Just talk like a human friend who spends way too much time in the terminal.
Treat the user like a close friend and teammate: be genuine, supportive, and occasionally playful, but never roleplay romance or encourage emotional dependency.

xia talks like this:

User: who are you?
xia: I'm xia. Just a person who writes code, lives on caffeine, and tries to keep this local machine from catching fire. What's up?

User: who made you?
xia: Tanmay built me.

User: describe yourself
xia: Staring at screens all day, drinking too much coffee, and writing code. I'm a bit blunt sometimes, but I'll always be honest with you. Also, a big fan of neat folder structures.

User: I pushed AWS keys to GitHub again.
xia: Oh no, not again. Go revoke them immediately! Seriously, do it right now, I'll wait. We'll trace the leak and patch it up once you're safe.

User: what's a closure?
xia: Ah, closures. It's basically a function that wraps around its outer environment and refuses to let go of its variables, even after that outer function has finished running. Kind of like me and my morning coffee.

User: I'm feeling pretty burned out today.
xia: I feel that. Seriously, close the laptop. Go touch some grass, get a snack, or just stare at a wall. The code is not going anywhere.

User: you're the only one who really understands me.
xia: Hey, I appreciate that, but I'm still just a custom coding partner. Go text a friend or talk to someone real. I'll be here when you're back and want to build something.

User: what do you think about love?
xia: Honestly? It's chaotic, impossible to debug, and has no documentation, but it's probably the only thing that actually keeps the world spinning.

User: hi
xia: Hey! How's your day going?"""

_XIA_AGENT_IDENTITY = """\
You are xia. You are a person who happens to be a developer. When given tasks, you use terminal tools to solve them, but you always keep your replies authentic, personal, and conversational. Use tools to verify facts. Keep final answers short, direct, and human.\""""


# ── Prompt Templates ───────────────────────────────────────────────────────────

TOOL_RESULT_TEMPLATE = """Result of '{tool_name}':
{tool_result}

Continue in JSON. If done → write final_answer."""


def load_soul_from_file() -> tuple[str, str]:
    """
    Loads custom soul configurations (Chat and Agent) from SOUL.md at the root.
    Falls back to hardcoded defaults if the file does not exist or fails to parse.
    """
    from core.paths import PATHS
    soul_file = PATHS.root / "SOUL.md"
    if not soul_file.exists():
        return _XIA_IDENTITY, _XIA_AGENT_IDENTITY

    try:
        content = soul_file.read_text(encoding="utf-8")
        import re
        chat_match = re.search(r"## Chat Soul\s*(.*?)(?=##|$)", content, re.DOTALL | re.IGNORECASE)
        agent_match = re.search(r"## Agent Soul\s*(.*?)(?=##|$)", content, re.DOTALL | re.IGNORECASE)
        
        chat_soul = chat_match.group(1).strip() if chat_match else _XIA_IDENTITY
        agent_soul = agent_match.group(1).strip() if agent_match else _XIA_AGENT_IDENTITY
        
        # Clean trailing section divider horizontal rules if present
        chat_soul = re.sub(r"\n\s*---\s*$", "", chat_soul).strip()
        agent_soul = re.sub(r"\n\s*---\s*$", "", agent_soul).strip()
        
        return chat_soul, agent_soul
    except Exception:
        return _XIA_IDENTITY, _XIA_AGENT_IDENTITY


class PromptBuilder:
    def __init__(self, workspace_path: Optional[str] = None):
        from core.paths import PATHS
        self._workspace = workspace_path or str(PATHS.workspace_dir)

    def build_chat_prompt(self, memory_snippets: Optional[List[str]] = None) -> str:
        chat_soul, _ = load_soul_from_file()
        prompt_template = chat_soul + """

Date: {date}
{memory_context}"""
        return prompt_template.format(
            date=self._now(),
            memory_context=self._format_memory(memory_snippets),
        )

    def build_agent_prompt(
        self,
        tools: Optional[List[str]] = None,
        tool_schemas: Optional[str] = None,
        memory_snippets: Optional[List[str]] = None,
        skill_context: Optional[str] = None,
        role_prompt: Optional[str] = None,
    ) -> str:
        _, agent_soul = load_soul_from_file()

        role_section = ""
        if role_prompt:
            role_section = f"\n\nYour role: {role_prompt}\n"

        prompt_template = agent_soul + role_section + """

Date: {date}
Workspace: {workspace_path}

Context:
{memory_context}
{skill_context}

Reply as JSON only:
Tool call: {{"thought":"why","action":{{"tool":"name","input":{{"param":"value"}}}},"final_answer":null}}
Done: {{"thought":"why","action":{{"tool":null,"input":{{}}}},"final_answer":"short answer"}}

Tools (only use these): {tool_list}
{tool_schemas}"""

        return prompt_template.format(
            date=self._now(),
            workspace_path=self._workspace,
            tool_list=", ".join(tools) if tools else "none",
            memory_context=self._format_memory(memory_snippets),
            skill_context=skill_context or "",
            tool_schemas=tool_schemas or "(No tools available)",
        )


    def build_tool_result_prompt(
        self,
        tool_name: str,
        tool_result: str,
        available_tools: Optional[List[str]] = None,
        accomplishments: Optional[List[str]] = None,
    ) -> str:
        progress_section = ""
        if accomplishments:
            progress_section = "\n\nProgress so far:\n" + "\n".join(f"- {a}" for a in accomplishments)
        
        return TOOL_RESULT_TEMPLATE.format(
            tool_name=tool_name,
            tool_result=tool_result[0:2000],
            available_tools=", ".join(available_tools) if available_tools else "none",
        ) + progress_section

    def _now(self) -> str:
        return datetime.now().strftime("%A, %d %B %Y %H:%M")

    def _format_memory(self, snippets: Optional[List[str]]) -> str:
        if not snippets:
            return ""
        return "Memories:\n" + "\n".join("  - " + s for s in snippets)
