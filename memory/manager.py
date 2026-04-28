"""
memory/manager.py — Memory Manager

High-level interface that ties together the store, embedder, and extractor.
This is what the agent and session interact with — they never touch
MemoryStore or MemoryExtractor directly.
"""

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from core.config import cfg
from core.logger import get_logger
from memory.graph import MemoryGraph
from memory.store import MemoryStore

log = get_logger(__name__)


class MemoryManager:
    """The single memory interface for the rest of xia."""

    def __init__(self, llm=None):
        self._llm = llm
        self._store = MemoryStore() if cfg.memory.enabled else None
        self._extractor = None
        self._graph = MemoryGraph() if getattr(cfg.memory, "graph_enabled", True) else None

        self._working_memory: Deque[str] = deque(maxlen=cfg.memory.working_memory_size)
        self._fast_cache: Dict[str, Tuple[float, List[str]]] = {}

        if self._store:
            log.info("MemoryManager ready: %d memories stored", self._store.count())
        else:
            log.info("Memory disabled in config")

        if self._graph:
            log.info("MemoryGraph ready: %d edges", self._graph.count_edges())

    # -- Retrieval ----------------------------------------------------------

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[str]:
        if not query or not query.strip():
            return []

        top_k = top_k or cfg.memory.max_results
        working_hits = self._retrieve_from_working_memory(query, top_k=top_k)
        graph_hits = self._retrieve_from_graph(query)

        if not self._store or not cfg.memory.enabled:
            return self._merge_unique(working_hits, graph_hits, top_k=top_k)

        cache_key = f"{self._normalize_query(query)}|{top_k}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return self._merge_unique(working_hits, cached, top_k=top_k)

        store_hits = self._store.retrieve(query, top_k=top_k)
        merged_store = self._merge_unique(store_hits, graph_hits, top_k=max(top_k, len(store_hits) + len(graph_hits)))
        self._set_cached(cache_key, merged_store)
        return self._merge_unique(working_hits, merged_store, top_k=top_k)

    # -- Storage ------------------------------------------------------------

    def remember(self, content: str, metadata: Optional[dict] = None) -> Optional[str]:
        if not self._store:
            return None

        metadata = metadata or {}
        metadata.setdefault("memory_type", "semantic")
        stored_id = self._store.add(content, metadata=metadata)

        if stored_id:
            self._touch_working_memory(content)
            self._maybe_add_graph_relation(metadata)
            self._invalidate_cache()

        return stored_id

    def remember_batch(self, items: List[str], metadata: Optional[dict] = None) -> List[str]:
        if not self._store:
            return []

        metadata = metadata or {}
        metadata.setdefault("memory_type", "semantic")
        stored = self._store.add_batch(items, metadata=metadata)

        if stored:
            for item in items:
                if item and item.strip():
                    self._touch_working_memory(item)
            self._maybe_add_graph_relation(metadata)
            self._invalidate_cache()

        return stored

    def save_session(self, session) -> int:
        if not self._store or not cfg.memory.enabled:
            return 0

        if not session or not session.messages:
            return 0

        raw_entries = self._extract_raw_memories(session)

        llm_entries: List[Dict] = []
        if self._llm and cfg.skills.auto_extract and getattr(cfg.memory, "typed_extraction_enabled", True):
            extractor = self._get_extractor()
            llm_entries = extractor.extract_typed_from_session(session)

        all_entries = raw_entries + llm_entries
        if not all_entries:
            return 0

        session_meta = {
            "session_id": session.session_id,
            "source": "session_end",
            "importance": 0.7,
        }

        stored = self._store.add_structured_batch(all_entries, base_metadata=session_meta)

        for entry in all_entries:
            text = str(entry.get("text", "")).strip()
            if text:
                self._touch_working_memory(text)

        self._ingest_graph_relations(all_entries, session_meta)
        self._invalidate_cache()

        log.info("Saved %d memories from session %s", len(stored), session.session_id)
        return len(stored)

    def track_interaction(self, user_input: str, assistant_output: str):
        if user_input and user_input.strip():
            self._touch_working_memory(f"User: {user_input.strip()[:300]}")
        if assistant_output and assistant_output.strip():
            self._touch_working_memory(f"Assistant: {assistant_output.strip()[:300]}")

    # -- Stats & management -------------------------------------------------

    def count(self) -> int:
        return self._store.count() if self._store else 0

    def recent(self, n: int = 5) -> List[str]:
        if not self._store:
            return []
        return [m.content for m in self._store.retrieve_recent(n)]

    def clear(self):
        if self._store:
            self._store.clear()
            self._working_memory.clear()
            self._invalidate_cache()
            if self._graph:
                self._graph.clear()
            log.warning("All memories cleared")

    def is_available(self) -> bool:
        return self._store is not None and cfg.memory.enabled

    # -- Internal -----------------------------------------------------------

    def _extract_raw_memories(self, session) -> List[Dict]:
        entries: List[Dict] = []

        for msg in session.messages:
            if msg.role != "user":
                continue

            content = msg.content.strip()
            if not content or len(content) < 10:
                continue

            lower = content.lower()

            memory_type = "episodic"
            importance = 0.50

            semantic_signals = (
                "my name is", "i am", "i'm", "i prefer", "i like", "i use",
                "my project", "i work", "i hate", "i love", "my favourite",
            )
            procedural_signals = (
                "how to", "steps", "workflow", "run this", "first", "then", "command",
            )

            if any(s in lower for s in semantic_signals):
                memory_type = "semantic"
                importance = 0.75
            elif any(s in lower for s in procedural_signals):
                memory_type = "procedural"
                importance = 0.70

            if any(s in lower for s in semantic_signals + procedural_signals):
                entries.append(
                    {
                        "text": f"User said: {content[:220]}",
                        "memory_type": memory_type,
                        "importance": importance,
                    }
                )

        return entries

    def _get_extractor(self):
        if self._extractor is None:
            from memory.extractor import MemoryExtractor
            self._extractor = MemoryExtractor(llm=self._llm)
        return self._extractor

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.lower().split())

    def _get_cached(self, key: str) -> Optional[List[str]]:
        ttl = cfg.memory.cache_ttl_seconds
        now = time.time()

        cached = self._fast_cache.get(key)
        if not cached:
            return None

        cached_at, values = cached
        if now - cached_at > ttl:
            self._fast_cache.pop(key, None)
            return None

        return values

    def _set_cached(self, key: str, values: List[str]):
        self._fast_cache[key] = (time.time(), list(values))

    def _invalidate_cache(self):
        self._fast_cache.clear()

    def _touch_working_memory(self, text: str):
        cleaned = text.strip()
        if cleaned:
            self._working_memory.append(cleaned)

    def _retrieve_from_working_memory(self, query: str, top_k: int) -> List[str]:
        if not self._working_memory:
            return []

        query_words = set(self._normalize_query(query).split())
        scored = []

        for idx, item in enumerate(reversed(self._working_memory)):
            item_words = set(item.lower().split())
            overlap = len(query_words & item_words)
            if overlap > 0:
                recency_bonus = max(0.0, 1.0 - (idx / max(1, cfg.memory.working_memory_size)))
                score = overlap + recency_bonus
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def _retrieve_from_graph(self, query: str) -> List[str]:
        if not self._graph:
            return []
        limit = getattr(cfg.memory, "graph_max_results", 3)
        return self._graph.retrieve_related(query, top_k=limit)

    def _maybe_add_graph_relation(self, metadata: Dict):
        if not self._graph or not metadata:
            return

        subject = str(metadata.get("subject", "")).strip()
        relation = str(metadata.get("relation", "")).strip()
        obj = str(metadata.get("object", "")).strip()

        if subject and relation and obj:
            self._graph.add_relation(subject, relation, obj, metadata=metadata)

    def _ingest_graph_relations(self, entries: List[Dict], base_metadata: Dict):
        if not self._graph:
            return

        rels = []
        for entry in entries:
            subject = str(entry.get("subject", "")).strip()
            relation = str(entry.get("relation", "")).strip()
            obj = str(entry.get("object", "")).strip()
            if not (subject and relation and obj):
                continue

            rel_meta = dict(base_metadata)
            rel_meta.update(
                {
                    "importance": entry.get("importance", 0.5),
                    "memory_type": entry.get("memory_type", "semantic"),
                }
            )
            rels.append({
                "subject": subject,
                "relation": relation,
                "object": obj,
                "metadata": rel_meta,
            })

        if rels:
            self._graph.add_relations(rels)

    def _merge_unique(self, first: List[str], second: List[str], top_k: int) -> List[str]:
        merged = []
        seen = set()

        for item in first + second:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= top_k:
                break

        return merged
