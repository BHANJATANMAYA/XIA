# XIA

XIA is a private, self-evolving AI brain that lives on your SSD: portable, fast, and built to understand you.

It runs locally with Ollama, keeps its memory on disk, and uses a layered memory system that combines short-term context, semantic recall, and local relationship hints without sending your data to the cloud.

## What XIA Does

- Runs local chat and task workflows with Ollama models
- Stores long-term memory with ChromaDB
- Keeps short-term working memory in RAM for smoother conversations
- Uses typed memories: episodic, semantic, and procedural
- Re-ranks memory retrieval using relevance, recency, and importance
- Maintains a local relationship graph for connected recall
- Stays portable by keeping models, memory, and config on your SSD

## Core Value

XIA is designed to stay:

- Private: no cloud dependency is required for memory or runtime
- Portable: models and memory can live inside the project SSD layout
- Fast: working memory and cache reduce unnecessary vector lookups
- Self-evolving: it learns from sessions and improves recall over time

## Quick Start

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Start Ollama

Make sure Ollama is installed and running locally.

### 3. Pull a model

```powershell
ollama pull mistral:latest
```

Other good options:

```powershell
ollama pull qwen2.5-coder:latest
ollama pull qwen3.5:4b
```

### 4. Launch XIA

```powershell
python main.py
```

If you use the Windows launcher, XIA can keep Ollama models under the local SSD path in `models/ollama/`.

## Model Management

To install a new model for XIA:

1. Pull it with Ollama, for example `ollama pull llama3.2:3b`
2. Confirm it exists with `ollama list`
3. Set it in [config.yaml](/D:/xia/config.yaml) under `llm.model`, or switch from the CLI
4. Restart XIA if needed

Model-related config and recommendations live in:

- [config.yaml](/D:/xia/config.yaml)
- [models/model_config.yaml](/D:/xia/models/model_config.yaml)

## CLI Commands

XIA supports these built-in commands:

- `/help` show available commands
- `/memory` inspect recent memory items
- `/remember <fact>` save a fact manually
- `/forget` clear stored memory
- `/save` persist the current session
- `/clear` clear the current chat screen/session context
- `/history` view recent session history
- `/models` list available local models
- `/model <name>` switch the current model
- `/use_model <name>` use a model for the current session
- `/set_default_model <name>` set the default startup model
- `/profile <name>` switch routing/profile behavior
- `/tools` list tool capabilities
- `/skills` list installed skills
- `/end` end the current session cleanly
- `/exit`, `/quit`, `/q` close XIA

## Memory System

XIA now uses a layered memory design:

1. Working memory in RAM for the latest interactions
2. Fast query cache for repeated lookups
3. ChromaDB for semantic long-term memory
4. A local JSON-backed graph for relationship hints
5. Re-ranking based on relevance, recency, and importance

Memory extraction is typed:

- `episodic`: conversation events
- `semantic`: durable facts and preferences
- `procedural`: workflows, instructions, and repeated how-to knowledge

More detail is documented in [README_MEMORY.md](/D:/xia/README_MEMORY.md).

## Project Structure

```text
xia/
|- agent/
|- core/
|- interface/
|- memory/
|  |- embedder.py
|  |- extractor.py
|  |- graph.py
|  |- manager.py
|  |- store.py
|- models/
|  |- model_config.yaml
|  |- ollama/
|- tools/
|- config.yaml
|- main.py
```

## Important Paths

- Config: [config.yaml](/D:/xia/config.yaml)
- Model catalog: [models/model_config.yaml](/D:/xia/models/model_config.yaml)
- Memory graph: `data/embeddings/memory_graph.json`
- Local Ollama storage: `models/ollama/`

## Documentation

- [README_MEMORY.md](/D:/xia/README_MEMORY.md): memory architecture, scoring, graph layer, config
- [README_OFFLINE.md](/D:/xia/README_OFFLINE.md): offline setup and local deployment notes
- [about.md](/D:/xia/about.md): project overview and higher-level positioning

## Current Direction

Recent cleanup and upgrades include:

- removal of the LeetCode-solving feature
- codebase cleanup and duplicate-path reduction
- memory v2 rollout with working memory, scoring, typed extraction, and graph hints
- improved local model and profile workflow

## Notes

XIA is built to remain local-first. If you extend it, prefer changes that preserve the same core principle:

`private, self-evolving, portable, fast`
