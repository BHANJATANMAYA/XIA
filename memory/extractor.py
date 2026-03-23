"""
memory/extractor.py — Memory Extractor

After each session, this scans the conversation and extracts
facts worth remembering for future sessions.

Instead of storing every message verbatim (wasteful and noisy),
it distills conversations into compact, reusable facts:

  "User prefers Python over JavaScript"
  "User is building a portable AI agent called xia"
  "User's name is Aryan, based in Mumbai"
  "User's SSD is mounted at D:\\xia"
  "Agent successfully created a notes.txt file using filesystem tool"

These extracted memories are what get injected into future prompts —
making xia feel like it actually knows you across sessions.

Usage:
    extractor = MemoryExtractor(llm)
    facts = extractor.extract(conversation_messages)
    # → ["User is building xia agent", "User prefers dark themes", ...]
"""

import json
from typing import List, Optional

from core.logger import get_logger

log = get_logger(__name__)

# Extraction prompt — asks the LLM to pull out memorable facts
EXTRACTION_PROMPT = """You are a memory extraction system for an AI agent called xia.

Given a conversation, extract facts that would be useful to remember in FUTURE conversations.

Extract facts about:
- User's name, location, preferences, habits
- Projects the user is working on (names, tech stack, goals)
- Things the user explicitly asked to remember
- Corrections the user made (e.g. "no, I prefer X over Y")
- Important decisions or outcomes from this session
- User's technical level and expertise areas

Do NOT extract:
- Trivial small talk
- Facts that are only relevant to this specific session
- Things the agent said (only what's notable about the user or their work)
- Duplicate facts already captured

Respond with ONLY a JSON array of strings. Each string is one fact, max 100 chars.
If nothing worth remembering, return an empty array.

Example output:
["User's name is Aryan", "User is building a portable AI system called xia on an external SSD", "User prefers Python 3.12", "Project root is D:\\\\xia"]

Conversation to extract from:
{conversation}"""


class MemoryExtractor:
    """
    Uses the LLM to extract memorable facts from conversations.
    Called at the end of each session automatically.
    """

    def __init__(self, llm=None):
        self._llm = llm  # Injected — avoids circular imports

    def extract(self, messages: List[dict], max_facts: int = 10) -> List[str]:
        """
        Extract memorable facts from a list of conversation messages.

        Args:
            messages: List of {"role": "user"/"assistant", "content": "..."}
            max_facts: Maximum facts to extract per session

        Returns:
            List of fact strings ready to store in memory.
        """
        if not messages or not self._llm:
            return []

        # Format conversation for the prompt
        conversation_text = self._format_conversation(messages)
        if not conversation_text.strip():
            return []

        log.info("Extracting memories from %d messages...", len(messages))

        try:
            result = self._llm.chat_json(
                EXTRACTION_PROMPT.format(conversation=conversation_text[:4000]),
            )

            # Handle both direct list and wrapped dict
            if isinstance(result, list):
                facts = result
            elif isinstance(result, dict):
                # Model might return {"facts": [...]} or {"memories": [...]}
                facts = (
                    result.get("facts") or
                    result.get("memories") or
                    result.get("items") or
                    []
                )
            else:
                facts = []

            # Validate and clean
            clean_facts = []
            for fact in facts[:max_facts]:
                if isinstance(fact, str) and fact.strip():
                    clean_facts.append(fact.strip()[:200])

            log.info("Extracted %d memories from session", len(clean_facts))
            return clean_facts

        except Exception as e:
            log.error("Memory extraction failed: %s", e)
            return []

    def extract_from_session(self, session) -> List[str]:
        """
        Convenience method — extract directly from a Session object.
        Called automatically at session end.
        """
        if not session or not session.messages:
            return []

        messages = [
            {"role": m.role, "content": m.content}
            for m in session.messages
        ]
        return self.extract(messages)

    def _format_conversation(self, messages: List[dict]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "").strip()
            if content:
                # Truncate very long messages
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"{role}: {content}")
        return "\n".join(lines)
