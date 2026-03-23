"""
memory/manager.py — Memory Manager

High-level interface that ties together the store, embedder, and extractor.
This is what the agent and session interact with — they never touch
MemoryStore or MemoryExtractor directly.

Responsibilities:
  - Store memories after each session
  - Retrieve relevant memories before each agent run
  - Auto-extract facts from conversations
  - Provide memory stats and management commands

Usage:
    manager = MemoryManager(llm=llm)

    # Retrieve before agent run
    snippets = manager.retrieve("help me with Python")

    # Save after session ends
    manager.save_session(session)
"""

from typing import List, Optional

from core.config import cfg
from core.logger import get_logger
from memory.store import MemoryStore

log = get_logger(__name__)


class MemoryManager:
    """
    The single memory interface for the rest of xia.
    Agent and Session only ever call this — never the store directly.
    """

    def __init__(self, llm=None):
        self._llm = llm
        self._store = MemoryStore() if cfg.memory.enabled else None
        self._extractor = None  # Lazy init to avoid import cycles

        if self._store:
            log.info("MemoryManager ready: %d memories stored", self._store.count())
        else:
            log.info("Memory disabled in config")

    # ── Retrieval ──────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[str]:
        """
        Get relevant memories for a query.
        Returns list of strings ready for system prompt injection.
        """
        if not self._store or not cfg.memory.enabled:
            return []
        return self._store.retrieve(query, top_k=top_k)

    # ── Storage ────────────────────────────────────────────────────────────

    def remember(self, content: str, metadata: Optional[dict] = None) -> Optional[str]:
        """Manually store a single memory."""
        if not self._store:
            return None
        return self._store.add(content, metadata=metadata)

    def remember_batch(self, items: List[str], metadata: Optional[dict] = None) -> List[str]:
        """Store multiple memories at once."""
        if not self._store:
            return []
        return self._store.add_batch(items, metadata=metadata)

    def save_session(self, session) -> int:
        """
        Auto-extract and store memorable facts from a completed session.
        Called at the end of every session automatically.
        Returns number of memories stored.
        """
        if not self._store or not cfg.memory.enabled:
            return 0

        if not session or not session.messages:
            return 0

        # Always store raw conversation summary
        raw_memories = self._extract_raw_memories(session)

        # Also use LLM to extract higher-quality facts if available
        llm_facts = []
        if self._llm and cfg.skills.auto_extract:
            extractor = self._get_extractor()
            llm_facts = extractor.extract_from_session(session)

        all_memories = raw_memories + llm_facts

        if all_memories:
            session_meta = {"session_id": session.session_id, "source": "session_end"}
            stored = self._store.add_batch(all_memories, metadata=session_meta)
            log.info("Saved %d memories from session %s", len(stored), session.session_id)
            return len(stored)

        return 0

    # ── Stats & management ─────────────────────────────────────────────────

    def count(self) -> int:
        """Total number of stored memories."""
        return self._store.count() if self._store else 0

    def recent(self, n: int = 5) -> List[str]:
        """Return N most recently stored memory strings."""
        if not self._store:
            return []
        return [m.content for m in self._store.retrieve_recent(n)]

    def clear(self):
        """Wipe all memories. Irreversible."""
        if self._store:
            self._store.clear()
            log.warning("All memories cleared")

    def is_available(self) -> bool:
        return self._store is not None and cfg.memory.enabled

    # ── Internal ───────────────────────────────────────────────────────────

    def _extract_raw_memories(self, session) -> List[str]:
        """
        Extract simple factual memories from session without LLM.
        These are always stored regardless of config.
        """
        memories = []

        for msg in session.messages:
            if msg.role != "user":
                continue

            content = msg.content.strip()
            if not content or len(content) < 10:
                continue

            # Store user messages that look like facts or preferences
            lower = content.lower()
            fact_signals = [
                "my name is", "i am", "i'm", "i prefer", "i like", "i use",
                "i work", "my project", "remember that", "don't forget",
                "always", "never", "i hate", "i love", "my favourite",
            ]
            if any(signal in lower for signal in fact_signals):
                memories.append(f"User said: {content[:200]}")

        return memories

    def _get_extractor(self):
        """Lazy-load the memory extractor."""
        if self._extractor is None:
            from memory.extractor import MemoryExtractor
            self._extractor = MemoryExtractor(llm=self._llm)
        return self._extractor
