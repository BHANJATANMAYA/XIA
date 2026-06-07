# XIA Memory Guide

This document explains XIA's current local memory architecture and how to tune it without breaking its core value:

`XIA is a private, self-evolving AI brain that lives on your SSD - portable, fast, and built to understand you.`

## Design Goals

- Keep everything local
- Preserve SSD portability
- Improve recall quality without cloud services
- Stay fast for repeated use

## Memory Layers

XIA uses a hybrid memory stack:

1. Working memory
   Stored in RAM as recent interactions for short-term continuity.
2. Fast cache
   A TTL-based query cache that avoids repeated semantic searches.
3. Long-term semantic memory
   Stored in ChromaDB with embeddings for recall by meaning.
4. Local relationship graph
   Stored in JSON for lightweight connected recall.

## Memory Types

XIA classifies extracted memories into three types:

- `episodic`
  Conversation events and session-specific moments.
- `semantic`
  Durable facts such as preferences, identity details, and stable user context.
- `procedural`
  Reusable workflows, habits, and how-to style knowledge.

These are extracted in [memory/extractor.py](/D:/xia/memory/extractor.py) and managed through [memory/manager.py](/D:/xia/memory/manager.py).

## Retrieval Pipeline

Current retrieval is multi-step:

1. Check working memory
2. Check fast cache
3. Query long-term vector memory
4. Pull related graph hints
5. Re-rank candidates before returning results

This gives XIA better continuity than raw vector search alone.

## Scoring

Long-term memories are not treated equally. XIA scores them using:

- relevance
- recency
- importance

Config weights are defined in [config.yaml](/D:/xia/config.yaml):

- `relevance_weight`
- `recency_weight`
- `importance_weight`
- `rerank_candidates`

Stored memory metadata also tracks:

- `memory_type`
- `importance`
- `last_accessed`
- `access_count`

## Relationship Graph

The graph layer is intentionally lightweight.

It stores local edges like:

- `User -> likes -> Python`
- `User -> interested_in -> AI`

Implementation:

- [memory/graph.py](/D:/xia/memory/graph.py)

Persistence path:

- `data/embeddings/memory_graph.json`

This is simpler and more portable than Neo4j, and is the right fit for XIA right now.

## Main Files

- [memory/store.py](/D:/xia/memory/store.py): vector storage, fallback, scoring, metadata
- [memory/manager.py](/D:/xia/memory/manager.py): working memory, cache, merge logic
- [memory/extractor.py](/D:/xia/memory/extractor.py): typed extraction rules
- [memory/graph.py](/D:/xia/memory/graph.py): local graph storage and related hints

## Configuration

Important memory settings in [config.yaml](/D:/xia/config.yaml):

- `working_memory_size`
- `cache_ttl_seconds`
- `rerank_candidates`
- `relevance_weight`
- `recency_weight`
- `importance_weight`
- `default_importance`
- `default_memory_type`
- `typed_extraction_enabled`
- `graph_enabled`
- `graph_max_results`

## Resetting Memory

If you want a clean start, clear memory from XIA or wipe the stored memory files and collections. This resets:

- vector memory
- graph memory
- cached recall state

Do this carefully if you want to preserve learned preferences.

## Future-Safe Guidance

Good next upgrades:

- stronger extraction heuristics
- better vectorless fallback like BM25
- migration-safe embedding upgrades

Upgrades to avoid unless clearly needed:

- heavy external graph databases
- anything that breaks local-first portability

The memory system should evolve, but the product promise should not.
