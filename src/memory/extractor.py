"""
memory/extractor.py — Memory Extractor

After each session, this scans the conversation and extracts
facts worth remembering for future sessions.
"""

from typing import Dict, List, Optional

from core.logger import get_logger

log = get_logger(__name__)

EXTRACTION_PROMPT = """You are a memory extraction system for an AI agent called xia.

Given a conversation, extract memories useful in future conversations.

For each memory, return an object with this schema:
{{
  "text": "short factual memory",
  "memory_type": "episodic|semantic|procedural",
  "importance": 0.0 to 1.0,
  "subject": "optional entity",
  "relation": "optional relation",
  "object": "optional entity"
}}

Guidelines:
- episodic: specific events/outcomes from this session
- semantic: stable facts/preferences/user profile/project facts
- procedural: step-by-step workflows, commands, or repeatable how-to knowledge
- importance: high for durable user preferences/goals, low for trivia
- keep text under 180 chars
- omit subject/relation/object when not clear

Do NOT extract trivial small talk.
Do NOT return duplicate memories.
Respond with ONLY a JSON array.

Conversation:
{conversation}
"""


class MemoryExtractor:
    """Uses the LLM to extract typed memorable facts from conversations."""

    VALID_TYPES = {"episodic", "semantic", "procedural"}

    def __init__(self, llm=None):
        self._llm = llm

    def extract(self, messages: List[dict], max_facts: int = 10) -> List[str]:
        """Backward-compatible plain-text extraction."""
        typed = self.extract_typed(messages, max_facts=max_facts)
        return [item["text"] for item in typed]

    def extract_typed(self, messages: List[dict], max_facts: int = 10) -> List[Dict]:
        """Extract typed memories with importance and optional relationships."""
        if not messages or not self._llm:
            return []

        conversation_text = self._format_conversation(messages)
        if not conversation_text.strip():
            return []

        log.info("Extracting typed memories from %d messages...", len(messages))

        try:
            result = self._llm.chat_json(
                EXTRACTION_PROMPT.format(conversation=conversation_text[:5000]),
            )
            items = self._normalize_result(result)

            cleaned: List[Dict] = []
            seen = set()
            for item in items:
                parsed = self._coerce_item(item)
                if not parsed:
                    continue

                key = parsed["text"].strip().lower()
                if key in seen:
                    continue
                seen.add(key)

                cleaned.append(parsed)
                if len(cleaned) >= max_facts:
                    break

            log.info("Extracted %d typed memories", len(cleaned))
            return cleaned

        except Exception as e:
            log.error("Typed memory extraction failed: %s", e)
            return []

    def extract_from_session(self, session) -> List[str]:
        """Backward-compatible extraction directly from Session."""
        return [item["text"] for item in self.extract_typed_from_session(session)]

    def extract_typed_from_session(self, session) -> List[Dict]:
        """Typed extraction directly from Session."""
        if not session or not session.messages:
            return []

        messages = [{"role": m.role, "content": m.content} for m in session.messages]
        return self.extract_typed(messages)

    def _normalize_result(self, result) -> List:
        if isinstance(result, list):
            return result

        if isinstance(result, dict):
            return (
                result.get("facts") or
                result.get("memories") or
                result.get("items") or
                []
            )

        return []

    def _coerce_item(self, item) -> Optional[Dict]:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                return None
            return {
                "text": text[:220],
                "memory_type": "semantic",
                "importance": 0.55,
            }

        if not isinstance(item, dict):
            return None

        text = str(item.get("text", "")).strip()
        if not text:
            return None

        memory_type = str(item.get("memory_type", "semantic")).strip().lower()
        if memory_type not in self.VALID_TYPES:
            memory_type = "semantic"

        try:
            importance = float(item.get("importance", 0.55))
        except Exception:
            importance = 0.55
        importance = max(0.0, min(1.0, importance))

        record = {
            "text": text[:220],
            "memory_type": memory_type,
            "importance": importance,
        }

        subject = str(item.get("subject", "")).strip()
        relation = str(item.get("relation", "")).strip()
        obj = str(item.get("object", "")).strip()

        if subject and relation and obj:
            record["subject"] = subject[:120]
            record["relation"] = relation[:120]
            record["object"] = obj[:120]

        return record

    def _format_conversation(self, messages: List[dict]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "").strip()
            if not content:
                continue
            if len(content) > 600:
                content = content[:600] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
