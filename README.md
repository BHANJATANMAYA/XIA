# xia — Portable Personal AI Agent

> A self-bootstrapping AI agent that lives entirely on an external SSD.  
> Plug in, double-click, and your personal AI is ready on any Windows machine.

---

## Quick Start

```bash
# 1. Plug in your SSD
# 2. Double-click launch.bat
# 3. That's it
```

First run automatically handles everything — Python, Ollama, dependencies, and model download (~4GB). Every run after that starts in seconds.

---

## What xia can do

- **Talk** — local LLM via Ollama, fully offline, no API keys needed
- **Remember** — stores memories across sessions using ChromaDB + embeddings
- **Act** — creates files, runs terminal commands, searches the web
- **Browse** — controls a real Chrome browser (Playwright)
- **Solve** — autonomous LeetCode solver with debug + retry loop
- **Learn** — extracts reusable skills from successful tasks automatically
- **Adapt** — detects host GPU/CPU and routes to the best available model

---

## Setup after cloning

```bash
# 1. Copy the env template
cp .env.example .env

# 2. Add your API keys (optional — DuckDuckGo search works without any key)
# TAVILY_API_KEY=...   ← best for AI search
# SERPAPI_KEY=...      ← alternative

# 3. Run the launcher — handles everything else
launch.bat
```

For browser features (Chrome automation + LeetCode):
```bash
.venv\Scripts\python install_browser.py
```

---

## Architecture

```
xia/
├── launch.bat                  # Entry point — double-click this
├── launch.py                   # Bootstrap: venv · deps · GPU · Ollama · health
├── main.py                     # Application entry point
├── config.yaml                 # All configuration
├── .env.example                # API key template (copy to .env)
│
├── core/                       # System foundation
│   ├── config.py               # Typed config loader
│   ├── paths.py                # Drive-letter agnostic path resolution
│   ├── logger.py               # Rotating file + console logging
│   ├── llm.py                  # Ollama client (streaming, history, JSON mode)
│   ├── prompt.py               # System prompt builder
│   ├── router.py               # Auto model-routing per task type
│   ├── health.py               # Startup health checks
│   ├── host.py                 # GPU/CPU/RAM detection
│   └── errors.py               # Structured error types
│
├── agent/                      # Reasoning engine
│   ├── agent.py                # THINK → PLAN → ACT → OBSERVE loop
│   ├── session.py              # Session manager + chat/agent routing
│   └── base.py                 # AgentStep · AgentResult · ToolCall types
│
├── tools/                      # Agent capabilities
│   ├── registry.py             # Tool registration + fuzzy name matching
│   ├── base.py                 # BaseTool contract
│   ├── filesystem.py           # Read · write · list · delete (sandboxed)
│   ├── terminal.py             # Shell commands with timeout + blocklist
│   ├── search.py               # Web search (Tavily / SerpAPI / DuckDuckGo)
│   ├── fetch.py                # Full page text extraction
│   ├── browser.py              # Playwright Chrome automation
│   └── leetcode.py             # LeetCode solve · debug · search loop
│
├── memory/                     # Persistent intelligence
│   ├── store.py                # ChromaDB vector store
│   ├── embedder.py             # sentence-transformers (all-MiniLM-L6-v2)
│   ├── extractor.py            # LLM-based fact extraction from sessions
│   └── manager.py              # High-level memory interface
│
├── skills/                     # Learned capabilities
│   ├── schema.py               # Skill data type
│   ├── store.py                # JSON file store + index
│   ├── extractor.py            # Auto-extract skills from successful tasks
│   └── manager.py              # Retrieve + inject skills into prompts
│
├── interface/                  # Terminal UI
│   ├── cli.py                  # Main interactive loop + all /commands
│   ├── renderer.py             # Rich-based output (steps · answers · tables)
│   └── theme.py                # Colours · icons · styles
│
├── models/
│   └── model_config.yaml       # Model registry (weights NOT stored here)
│
├── data/                       # Persistent data — not committed to git
│   ├── conversations/          # Session transcripts (JSON)
│   ├── embeddings/             # ChromaDB vector database
│   └── skills_store/           # Extracted skills (JSON)
│
├── workspace/                  # Agent's working folder for user files
└── logs/                       # Rotating runtime logs
```

---

## CLI Commands

| Command | Description |
|---|---|
| `/memory` | Show stored memories |
| `/remember <fact>` | Manually store a memory |
| `/forget` | Clear all memories |
| `/skills` | List learned skills |
| `/tools` | List available tools |
| `/models` | Show all downloaded Ollama models |
| `/model <name>` | Switch to a specific model |
| `/profile <name>` | Switch profile: `coding` · `fast` · `smart` · `default` |
| `/save` | Save session to disk now |
| `/clear` | Clear conversation history |
| `/help` | Show all commands |

---

## Multi-model routing

xia automatically picks the best available model based on the task:

| Profile | Best for | Prefers |
|---|---|---|
| `coding` | Code, algorithms, LeetCode | `qwen2.5-coder`, `deepseek-coder` |
| `fast` | Quick questions | `phi4`, `phi3` |
| `smart` | Deep reasoning | `deepseek-r1`, `llama3.1` |
| `default` | General use | `mistral`, `llama3` |

Pull any model and xia will start using it automatically:
```bash
ollama pull qwen2.5-coder
ollama pull phi4
ollama pull deepseek-r1
```

---

## System Requirements

| | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 | Windows 11 |
| RAM | 8GB | 16GB+ |
| SSD free space | 30GB | 60GB+ |
| SSD interface | USB 3.0 | USB 3.1 / NVMe |
| GPU | — | Any NVIDIA (CUDA auto-detected) |
| Python | 3.11+ | 3.12 |

xia adapts to whatever hardware is available. GPU is optional — CPU-only works fine.

---

## Design Principles

- **Everything on the SSD** — code, models, memory, skills, logs. Nothing touches the host machine permanently.
- **Drive-letter agnostic** — works whether the SSD mounts as `D:`, `E:`, `F:`, or anything else.
- **Self-healing** — health checks on every launch catch problems before they become crashes.
- **No cloud dependency** — runs 100% locally by default. Internet only used for web search.
- **No retraining** — memory and skills improve responses without touching model weights.
- **Modular** — every component is independently replaceable. Swap ChromaDB for another vector store, swap Ollama for llama.cpp, swap the CLI for a web UI.

---

## Build log

| Part | What was built |
|---|---|
| 1 | Project scaffold, SSD layout, config system, path resolution |
| 2 | Self-bootstrapping Windows launcher (venv, deps, Ollama, model pull) |
| 3 | Ollama LLM client — streaming, history, JSON mode, model switching |
| 4 | Agentic loop — THINK → PLAN → ACT → OBSERVE, session routing |
| 5 | Tool system — filesystem, terminal, tool registry, sandboxed paths |
| 6 | Web search (Tavily/DDG) + page fetcher |
| 7 | Persistent memory — ChromaDB, sentence-transformers, semantic retrieval |
| 8 | Skill system — auto-extraction, JSON store, prompt injection |
| 9 | Rich terminal UI — coloured steps, markdown panels, all /commands |
| 10 | Robustness — health checks, GPU detection, structured errors |
| 11 | Browser automation (Playwright) + LeetCode autonomous solver |
| +  | Multi-model routing — auto-pick model per task, /profile command |

---

## License

MIT