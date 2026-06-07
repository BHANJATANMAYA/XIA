"""
memory/graph.py — Local Relationship Graph

Lightweight graph memory that remains fully local.
Stores subject-relation-object edges in JSON on SSD and keeps an in-memory index.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from core.logger import get_logger
from core.paths import PATHS

log = get_logger(__name__)


class MemoryGraph:
    def __init__(self):
        self._path = PATHS.embeddings_dir / "memory_graph.json"
        self._nodes = set()
        self._edges: List[Dict] = []
        self._load()

    def add_relation(
        self,
        subject: str,
        relation: str,
        obj: str,
        metadata: Optional[Dict] = None,
    ) -> bool:
        subject = (subject or "").strip()
        relation = (relation or "").strip()
        obj = (obj or "").strip()

        if not subject or not relation or not obj:
            return False

        edge = {
            "subject": subject[:120],
            "relation": relation[:120],
            "object": obj[:120],
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        key = self._edge_key(edge)
        for existing in self._edges:
            if self._edge_key(existing) == key:
                # Keep latest metadata/timestamp without duplicating the edge.
                existing["created_at"] = edge["created_at"]
                existing["metadata"] = edge["metadata"]
                self._save()
                return True

        self._edges.append(edge)
        self._nodes.add(subject)
        self._nodes.add(obj)
        self._save()
        return True

    def add_relations(self, relations: List[Dict]) -> int:
        if not relations:
            return 0

        added = 0
        for rel in relations:
            if self.add_relation(
                rel.get("subject", ""),
                rel.get("relation", ""),
                rel.get("object", ""),
                metadata=rel.get("metadata"),
            ):
                added += 1
        return added

    def retrieve_related(self, query: str, top_k: int = 3) -> List[str]:
        query = (query or "").strip().lower()
        if not query or not self._edges:
            return []

        query_words = set(query.split())
        scored = []

        for edge in self._edges:
            s = edge["subject"].lower()
            r = edge["relation"].lower()
            o = edge["object"].lower()
            text = f"{edge['subject']} -> {edge['relation']} -> {edge['object']}"

            edge_words = set((s + " " + r + " " + o).split())
            overlap = len(query_words & edge_words)
            if overlap == 0 and query not in s and query not in o and query not in r:
                continue

            # Favor newer edges slightly.
            recency_bonus = 0.2
            try:
                age_sec = (datetime.now() - datetime.fromisoformat(edge["created_at"])).total_seconds()
                recency_bonus = max(0.0, 0.2 - (age_sec / 86400.0) * 0.01)
            except Exception:
                pass

            importance = 0.5
            try:
                importance = float(edge.get("metadata", {}).get("importance", 0.5))
            except Exception:
                pass

            score = overlap + recency_bonus + importance * 0.5
            scored.append((score, text))

        scored.sort(key=lambda x: x[0], reverse=True)

        seen = set()
        results = []
        for _, text in scored:
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(f"Graph: {text}")
            if len(results) >= top_k:
                break

        return results

    def count_edges(self) -> int:
        return len(self._edges)

    def clear(self):
        self._edges = []
        self._nodes = set()
        self._save()

    def _edge_key(self, edge: Dict) -> str:
        return "|".join([
            edge.get("subject", "").strip().lower(),
            edge.get("relation", "").strip().lower(),
            edge.get("object", "").strip().lower(),
        ])

    def _load(self):
        if not self._path.exists():
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            edges = raw.get("edges", []) if isinstance(raw, dict) else []
            self._edges = [e for e in edges if isinstance(e, dict)]
            self._nodes = set()
            for edge in self._edges:
                self._nodes.add(edge.get("subject", ""))
                self._nodes.add(edge.get("object", ""))
            log.info("MemoryGraph loaded: %d edges", len(self._edges))
        except Exception as e:
            log.warning("Could not load memory graph: %s", e)
            self._edges = []
            self._nodes = set()

    def _save(self):
        try:
            payload = {
                "version": 1,
                "saved_at": datetime.now().isoformat(),
                "edges": self._edges,
            }
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            log.error("Could not save memory graph: %s", e)
