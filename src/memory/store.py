"""
memory/store.py — Persistent Memory Store

xia's long-term memory. Stores conversations and facts as vector embeddings
so semantically similar content can be retrieved in future sessions.

Built on ChromaDB — a lightweight vector database that runs entirely on the SSD.
No server needed, no cloud, just files on disk.
"""

import json
import math
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
        self.id = memory_id or str(uuid.uuid4())
        self.content = content
        self.metadata = metadata or {}
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
        self._client = None
        self._fallback_store: List[Dict] = []
        self._fallback_path = PATHS.embeddings_dir / "fallback_memory.json"
        self._use_fallback = False

        self._init_store()

    # -- Public API ---------------------------------------------------------

    def add(self, content: str, metadata: Optional[Dict] = None) -> Optional[str]:
        if not content or not content.strip():
            return None

        content = content.strip()
        memory_id = str(uuid.uuid4())
        meta = self._build_metadata(metadata or {}, default_source="session")

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
            return memory_id
        except Exception as e:
            log.error("Failed to store memory: %s", e)
            return None

    def add_batch(self, items: List[str], metadata: Optional[Dict] = None) -> List[str]:
        if not items:
            return []

        clean = [t.strip() for t in items if t and t.strip()]
        if not clean:
            return []

        ids = [str(uuid.uuid4()) for _ in clean]
        meta_list = [self._build_metadata(metadata or {}, default_source="batch") for _ in clean]

        if self._use_fallback:
            out = []
            for i, c, m in zip(ids, clean, meta_list):
                stored = self._fallback_add(i, c, m)
                if stored:
                    out.append(stored)
            return out

        try:
            vectors = self.embedder.embed_batch(clean)
            self._collection.add(ids=ids, embeddings=vectors, documents=clean, metadatas=meta_list)
            return ids
        except Exception as e:
            log.error("Batch store failed: %s", e)
            return []

    def add_structured_batch(self, entries: List[Dict], base_metadata: Optional[Dict] = None) -> List[str]:
        """Store structured memory entries with per-entry metadata."""
        if not entries:
            return []

        docs: List[str] = []
        metas: List[Dict] = []

        for entry in entries:
            text = str(entry.get("text", "")).strip()
            if not text:
                continue

            merged = dict(base_metadata or {})
            merged.update({
                "memory_type": entry.get("memory_type", merged.get("memory_type")),
                "importance": entry.get("importance", merged.get("importance")),
            })

            if entry.get("subject") and entry.get("relation") and entry.get("object"):
                merged["subject"] = str(entry.get("subject")).strip()[:120]
                merged["relation"] = str(entry.get("relation")).strip()[:120]
                merged["object"] = str(entry.get("object")).strip()[:120]

            docs.append(text)
            metas.append(self._build_metadata(merged, default_source="structured"))

        if not docs:
            return []

        ids = [str(uuid.uuid4()) for _ in docs]

        if self._use_fallback:
            out = []
            for i, d, m in zip(ids, docs, metas):
                stored = self._fallback_add(i, d, m)
                if stored:
                    out.append(stored)
            return out

        try:
            vectors = self.embedder.embed_batch(docs)
            self._collection.add(ids=ids, embeddings=vectors, documents=docs, metadatas=metas)
            return ids
        except Exception as e:
            log.error("Structured batch store failed: %s", e)
            return []

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_similarity: Optional[float] = None,
    ) -> List[str]:
        if not query or not query.strip():
            return []

        top_k = top_k or cfg.memory.max_results
        min_similarity = min_similarity if min_similarity is not None else cfg.memory.similarity_threshold
        candidate_count = max(top_k, getattr(cfg.memory, "rerank_candidates", 20))

        if self._use_fallback:
            return self._fallback_retrieve(query, top_k)

        try:
            count = self._collection.count()
            if count == 0:
                return []

            vector = self.embedder.embed(query)
            results = self._collection.query(
                query_embeddings=[vector],
                n_results=min(candidate_count, count),
                include=["documents", "distances", "metadatas"],
            )

            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            ids = results.get("ids", [[]])[0]

            ranked = []
            touched_ids = []
            touched_meta = []

            for mem_id, doc, dist, meta in zip(ids, documents, distances, metadatas):
                similarity = self._distance_to_similarity(dist)
                if similarity < min_similarity:
                    continue

                meta = meta or {}
                recency = self._recency_score(meta.get("last_accessed") or meta.get("created_at"))
                importance = self._safe_float(meta.get("importance"), cfg.memory.default_importance)

                final_score = (
                    similarity * cfg.memory.relevance_weight +
                    recency * cfg.memory.recency_weight +
                    importance * cfg.memory.importance_weight
                )
                ranked.append((final_score, doc, mem_id, meta))

            ranked.sort(key=lambda x: x[0], reverse=True)
            selected = ranked[:top_k]

            for _, _, mem_id, meta in selected:
                touched_ids.append(mem_id)
                touched_meta.append(meta)

            self._touch_access_metadata(touched_ids, touched_meta)
            return [doc for _, doc, _, _ in selected]

        except Exception as e:
            log.error("Memory retrieval failed: %s", e)
            return []

    def retrieve_recent(self, n: int = 10) -> List[Memory]:
        if self._use_fallback:
            recent = sorted(self._fallback_store, key=lambda x: x["created_at"], reverse=True)
            return [Memory(r["content"], r["id"], r["metadata"], r["created_at"]) for r in recent[:n]]

        try:
            results = self._collection.get(include=["documents", "metadatas"])
            items = list(zip(results.get("ids", []), results.get("documents", []), results.get("metadatas", [])))
            items.sort(key=lambda x: x[2].get("created_at", ""), reverse=True)
            return [Memory(doc, mid, meta, meta.get("created_at")) for mid, doc, meta in items[:n]]
        except Exception as e:
            log.error("retrieve_recent failed: %s", e)
            return []

    def count(self) -> int:
        if self._use_fallback:
            return len(self._fallback_store)
        try:
            return self._collection.count()
        except Exception:
            return 0

    def delete(self, memory_id: str) -> bool:
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

    # -- Init ---------------------------------------------------------------

    def _init_store(self):
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
                self._collection.count(), self.collection_name,
            )
        except ImportError:
            log.warning("ChromaDB not installed — falling back to JSON memory store")
            self._use_fallback = True
            self._load_fallback()
        except Exception as e:
            log.error("ChromaDB init failed: %s — falling back to JSON", e)
            self._use_fallback = True
            self._load_fallback()

    # -- Retrieval helpers --------------------------------------------------

    def _distance_to_similarity(self, distance: float) -> float:
        similarity = 1.0 - (distance / 2.0)
        return max(0.0, min(1.0, similarity))

    def _recency_score(self, iso_timestamp: Optional[str]) -> float:
        if not iso_timestamp:
            return 0.5
        try:
            dt = datetime.fromisoformat(iso_timestamp)
            age_days = max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
            return math.exp(-age_days / 30.0)
        except Exception:
            return 0.5

    def _safe_float(self, value, default: float) -> float:
        try:
            v = float(value)
            return max(0.0, min(1.0, v))
        except Exception:
            return default

    def _build_metadata(self, metadata: Dict, default_source: str) -> Dict:
        now = datetime.now().isoformat()
        importance = self._safe_float(metadata.get("importance"), cfg.memory.default_importance)

        built = {
            "created_at": metadata.get("created_at", now),
            "last_accessed": metadata.get("last_accessed", now),
            "access_count": int(metadata.get("access_count", 0)),
            "importance": importance,
            "memory_type": metadata.get("memory_type", cfg.memory.default_memory_type),
            "source": metadata.get("source", default_source),
            **metadata,
        }

        if built.get("subject"):
            built["subject"] = str(built["subject"])[:120]
        if built.get("relation"):
            built["relation"] = str(built["relation"])[:120]
        if built.get("object"):
            built["object"] = str(built["object"])[:120]

        return built

    def _touch_access_metadata(self, ids: List[str], metadatas: List[Dict]):
        if not ids or self._use_fallback:
            return

        now = datetime.now().isoformat()
        updated = []
        for meta in metadatas:
            m = dict(meta or {})
            m["last_accessed"] = now
            m["access_count"] = int(m.get("access_count", 0)) + 1
            updated.append(m)

        try:
            self._collection.update(ids=ids, metadatas=updated)
        except Exception as e:
            log.debug("Could not update access metadata: %s", e)

    # -- JSON fallback ------------------------------------------------------

    def _fallback_add(self, memory_id: str, content: str, meta: dict) -> str:
        self._fallback_store.append(
            {
                "id": memory_id,
                "content": content,
                "metadata": meta,
                "created_at": meta.get("created_at", datetime.now().isoformat()),
            }
        )
        self._save_fallback()
        return memory_id

    def _fallback_retrieve(self, query: str, top_k: int) -> List[str]:
        if not self._fallback_store:
            return []

        query_words = set(query.lower().split())
        scored = []

        for item in self._fallback_store:
            content = item.get("content", "")
            content_words = set(content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                scored.append((overlap, content))

        scored.sort(reverse=True)
        return [content for _, content in scored[:top_k]]

    def _load_fallback(self):
        if self._fallback_path.exists():
            try:
                self._fallback_store = json.loads(self._fallback_path.read_text(encoding="utf-8"))
                log.info("Fallback memory loaded: %d entries", len(self._fallback_store))
            except Exception:
                self._fallback_store = []

    def _save_fallback(self):
        try:
            self._fallback_path.write_text(json.dumps(self._fallback_store, indent=2), encoding="utf-8")
        except Exception as e:
            log.error("Could not save fallback memory: %s", e)
