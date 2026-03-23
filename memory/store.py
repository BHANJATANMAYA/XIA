"""
memory/store.py — Persistent Memory Store

xia's long-term memory. Stores conversations and facts as vector embeddings
so semantically similar content can be retrieved in future sessions.

Built on ChromaDB — a lightweight vector database that runs entirely on the SSD.
No server needed, no cloud, just files on disk.

How it works:
  1. After each session, important exchanges are saved as memories
  2. Each memory is embedded into a 384-dim vector
  3. When the agent gets a new task, the top-K most similar memories are retrieved
  4. Those memories are injected into the system prompt as context

What gets stored:
  - Conversations (user questions + agent answers)
  - Extracted facts (user preferences, project details, corrections)
  - Task outcomes (what worked, what failed)

Usage:
    store = MemoryStore()
    store.add("User's name is Aryan and they prefer Python")
    results = store.retrieve("what does the user prefer?", top_k=3)
    # → ["User's name is Aryan and they prefer Python"]
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from core.config import cfg
from core.logger import get_logger
from core.paths import PATHS
from memory.embedder import Embedder

log = get_logger(__name__)


class Memory:
    """A single stored memory."""
    def __init__(
        self,
        content: str,
        memory_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        created_at: Optional[str] = None,
    ):
        self.id         = memory_id or str(uuid.uuid4())
        self.content    = content
        self.metadata   = metadata or {}
        self.created_at = created_at or datetime.now().isoformat()

    def __repr__(self) -> str:
        return f"Memory({self.content[:60]}...)"


class MemoryStore:
    """
    Vector-backed persistent memory store.
    Wraps ChromaDB with a clean interface for the agent.
    Falls back to a simple JSON store if ChromaDB isn't available.
    """

    def __init__(self, collection_name: Optional[str] = None):
        self.collection_name = collection_name or cfg.memory.collection_name
        self.embedder = Embedder()
        self._collection = None
        self._fallback_store: List[Dict] = []
        self._fallback_path = PATHS.embeddings_dir / "fallback_memory.json"
        self._use_fallback = False

        self._init_store()

    # ── Public API ─────────────────────────────────────────────────────────

    def add(
        self,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """
        Store a new memory.

        Args:
            content:  The text to remember.
            metadata: Optional tags (source, session_id, type, etc.)

        Returns:
            The memory ID, or None on failure.
        """
        if not content or not content.strip():
            return None

        content = content.strip()
        memory_id = str(uuid.uuid4())
        meta = {
            "created_at": datetime.now().isoformat(),
            "source": "session",
            **(metadata or {}),
        }

        if self._use_fallback:
            return self._fallback_add(memory_id, content, meta)

        try:
            vector = self.embedder.embed(content)
            self._collection.add(
                ids=[memory_id],
                embeddings=[vector],
                documents=[content],
                metadatas=[meta],
            )
            log.debug("Memory stored: %s...", content[:60])
            return memory_id
        except Exception as e:
            log.error("Failed to store memory: %s", e)
            return None

    def add_batch(self, items: List[str], metadata: Optional[Dict] = None) -> List[str]:
        """Store multiple memories efficiently."""
        if not items:
            return []

        clean = [t.strip() for t in items if t and t.strip()]
        if not clean:
            return []

        ids = [str(uuid.uuid4()) for _ in clean]
        meta_list = [
            {"created_at": datetime.now().isoformat(), "source": "batch", **(metadata or {})}
            for _ in clean
        ]

        if self._use_fallback:
            return [self._fallback_add(i, c, m) for i, c, m in zip(ids, clean, meta_list)]

        try:
            vectors = self.embedder.embed_batch(clean)
            self._collection.add(
                ids=ids,
                embeddings=vectors,
                documents=clean,
                metadatas=meta_list,
            )
            log.debug("Batch stored: %d memories", len(clean))
            return ids
        except Exception as e:
            log.error("Batch store failed: %s", e)
            return []

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_similarity: Optional[float] = None,
    ) -> List[str]:
        """
        Retrieve the most relevant memories for a query.

        Returns a list of memory strings, most relevant first.
        Empty list if nothing relevant found or memory is empty.
        """
        if not query or not query.strip():
            return []

        top_k = top_k or cfg.memory.max_results
        min_similarity = min_similarity or cfg.memory.similarity_threshold

        if self._use_fallback:
            return self._fallback_retrieve(query, top_k)

        try:
            count = self._collection.count()
            if count == 0:
                return []

            vector = self.embedder.embed(query)
            results = self._collection.query(
                query_embeddings=[vector],
                n_results=min(top_k, count),
                include=["documents", "distances"],
            )

            memories = []
            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for doc, dist in zip(documents, distances):
                # ChromaDB uses L2 distance — convert to similarity score
                # Distance 0 = identical, distance 2 = opposite
                similarity = 1.0 - (dist / 2.0)
                if similarity >= min_similarity:
                    memories.append(doc)

            log.debug("Retrieved %d memories for query: %s...", len(memories), query[:40])
            return memories

        except Exception as e:
            log.error("Memory retrieval failed: %s", e)
            return []

    def retrieve_recent(self, n: int = 10) -> List[Memory]:
        """Return the N most recently stored memories."""
        if self._use_fallback:
            recent = sorted(self._fallback_store, key=lambda x: x["created_at"], reverse=True)
            return [Memory(r["content"], r["id"], r["metadata"], r["created_at"]) for r in recent[:n]]

        try:
            results = self._collection.get(include=["documents", "metadatas"])
            items = list(zip(
                results.get("ids", []),
                results.get("documents", []),
                results.get("metadatas", []),
            ))
            items.sort(key=lambda x: x[2].get("created_at", ""), reverse=True)
            return [
                Memory(doc, mid, meta, meta.get("created_at"))
                for mid, doc, meta in items[:n]
            ]
        except Exception as e:
            log.error("retrieve_recent failed: %s", e)
            return []

    def count(self) -> int:
        """Return total number of stored memories."""
        if self._use_fallback:
            return len(self._fallback_store)
        try:
            return self._collection.count()
        except Exception:
            return 0

    def delete(self, memory_id: str) -> bool:
        """Delete a specific memory by ID."""
        if self._use_fallback:
            self._fallback_store = [m for m in self._fallback_store if m["id"] != memory_id]
            self._save_fallback()
            return True
        try:
            self._collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            log.error("Delete failed: %s", e)
            return False

    def clear(self):
        """Wipe all memories. Use with caution."""
        if self._use_fallback:
            self._fallback_store = []
            self._save_fallback()
            return
        try:
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "l2"},
            )
            log.info("Memory store cleared")
        except Exception as e:
            log.error("Clear failed: %s", e)

    # ── Init ───────────────────────────────────────────────────────────────

    def _init_store(self):
        """Initialise ChromaDB, fall back to JSON if unavailable."""
        try:
            import chromadb
            from chromadb.config import Settings

            db_path = str(PATHS.embeddings_dir)
            self._client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "l2"},
            )
            log.info(
                "MemoryStore initialised (ChromaDB): %d memories in '%s'",
                self._collection.count(), self.collection_name
            )

        except ImportError:
            log.warning("ChromaDB not installed — falling back to JSON memory store")
            self._use_fallback = True
            self._load_fallback()

        except Exception as e:
            log.error("ChromaDB init failed: %s — falling back to JSON", e)
            self._use_fallback = True
            self._load_fallback()

    # ── JSON fallback (used if ChromaDB unavailable) ───────────────────────

    def _fallback_add(self, memory_id: str, content: str, meta: dict) -> str:
        self._fallback_store.append({
            "id": memory_id,
            "content": content,
            "metadata": meta,
            "created_at": meta.get("created_at", datetime.now().isoformat()),
        })
        self._save_fallback()
        return memory_id

    def _fallback_retrieve(self, query: str, top_k: int) -> List[str]:
        """Simple keyword-based retrieval for fallback mode."""
        if not self._fallback_store:
            return []
        query_words = set(query.lower().split())
        scored = []
        for item in self._fallback_store:
            content_words = set(item["content"].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                scored.append((overlap, item["content"]))
        scored.sort(reverse=True)
        return [content for _, content in scored[:top_k]]

    def _load_fallback(self):
        if self._fallback_path.exists():
            try:
                self._fallback_store = json.loads(self._fallback_path.read_text())
                log.info("Fallback memory loaded: %d entries", len(self._fallback_store))
            except Exception:
                self._fallback_store = []

    def _save_fallback(self):
        try:
            self._fallback_path.write_text(json.dumps(self._fallback_store, indent=2))
        except Exception as e:
            log.error("Could not save fallback memory: %s", e)
