# 🚀 XIA — eXtremely Intelligent Assistant
### Comprehensive Project Overview

> A self-bootstrapping, portable AI agent that runs entirely from an external SSD.
> Plug in. Double-click. Your personal AI is ready — anywhere.

---

## 📌 What Is XIA?

XIA (eXtremely Intelligent Assistant) is a **fully offline, portable, self-contained AI agent system** built entirely in Python. It runs from an external SSD without requiring any pre-installed software on the host machine. On the first launch, it bootstraps its own Python virtual environment, installs all dependencies, downloads the Ollama runtime, and pulls LLM models automatically. On every subsequent run, it starts instantly.

XIA is not just a chatbot — it is a **reasoning agent** that can think, plan, act using real-world tools, observe results, and learn from experience. It uses a local LLM (via Ollama) so all computation is 100% private and offline.

---

## 🎯 Core Philosophy

| Principle | Description |
|---|---|
| **Portable** | Lives entirely on an SSD — plug in anywhere, works instantly |
| **Zero host dependency** | Installs everything itself on first run |
| **Local-first** | No API calls to cloud LLMs — full privacy |
| **Self-healing** | Health checks and automatic recovery at startup |
| **Modular** | Every subsystem is independently replaceable |
| **Learning** | Extracts and reuses skills from successful past tasks |

---

## 🧠 What XIA Can Do

| Capability | Description |
|---|---|
| 💬 **Chat** | Multi-turn conversation with a local LLM via Ollama |
| 🧠 **Remember** | Persistent semantic memory stored in ChromaDB (survives restarts) |
| ⚡ **Act** | Execute real file operations, shell commands, and desktop automation |
| 🌐 **Browse** | Control a real Chrome browser via Playwright |

| 📚 **Learn** | Auto-extracts reusable skills from completed tasks |
| ⚙️ **Adapt** | GPU/CPU-aware model routing, adaptive temperature |
| 🔍 **Search** | Web search via Tavily, SerpAPI, or DuckDuckGo |
| 📄 **Fetch** | Full-page text extraction from any URL |

---

## 🏗️ Architecture Overview

XIA is built on a layered, modular architecture inspired by the C4 model:

```
User Input
    │
    ▼
CLI Interface  (interface/)
    │
    ▼
Session Manager  (agent/session.py)
    │         │
    ▼         ▼
Agent Core   Chat Mode
(agent/agent.py)
    │
    ├── Model Router  (core/router.py)
    ├── Prompt Builder (core/prompt.py)
    ├── Memory Manager (memory/manager.py)
    ├── Skill Manager  (skills/manager.py)
    └── Tool Registry  (tools/registry.py)
              │
    ┌─────────┼──────────┬──────────┐
    ▼         ▼          ▼          ▼
 File      Terminal   Browser    Search
 Tool       Tool       Tool       Tool
```

### Agent Reasoning Loop

The agent follows a structured THINK → PLAN → ACT → OBSERVE cycle:

1. **THINK** — The LLM reasons about the task in JSON format
2. **PLAN** — On the first iteration, a multi-step plan is emitted
3. **ACT** — The LLM picks a tool and calls it with structured arguments
4. **OBSERVE** — The tool result is fed back into context
5. **REPEAT** — The loop continues until a `final_answer` is produced
6. **LEARN** — On success, a skill is auto-extracted and stored

Max iterations per task: configurable (default: 10). Max retries on tool failure: 3.

---

## 📁 Project Structure

```
xia/
├── launch.bat              # Entry point — double-click to start
├── launch.py               # Bootstrap: venv, deps, GPU detect, Ollama, model pull
├── main.py                 # Application entry point
├── config.yaml             # All configuration (LLM, agent, memory, skills, tools)
├── .env / .env.example     # Optional API keys (Tavily, SerpAPI)
│
├── core/                   # System foundation layer
│   ├── config.py           # Typed config loader (Pydantic-style YAML)
│   ├── paths.py            # Drive-letter agnostic SSD path resolution
│   ├── logger.py           # Rotating file + console logging
│   ├── llm.py              # Ollama LLM client (streaming, JSON, history)
│   ├── prompt.py           # System prompt builder with memory + skills injection
│   ├── router.py           # Auto model routing per task type
│   ├── health.py           # Startup health checks (Ollama, models, disk space)
│   ├── host.py             # GPU/CPU/RAM hardware detection
│   └── errors.py           # Structured custom error types
│
├── agent/                  # Reasoning engine
│   ├── agent.py            # THINK→PLAN→ACT→OBSERVE agentic loop
│   ├── session.py          # Session manager + chat vs. agent mode routing
│   └── base.py             # AgentStep, AgentResult, ToolCall, AgentDecision types
│
├── tools/                  # Agent capabilities (tool system)
│   ├── registry.py         # Tool registration + fuzzy name matching
│   ├── base.py             # BaseTool abstract contract + ToolSchema
│   ├── filesystem.py       # Sandboxed read/write/list/delete file operations
│   ├── terminal.py         # Shell command executor with timeout + blocklist
│   ├── search.py           # Web search (Tavily / SerpAPI / DuckDuckGo)
│   ├── fetch.py            # Full page text extraction from URLs
│   ├── browser.py          # Playwright Chrome browser automation
│   └── __init__.py         # Tools package marker
│
├── memory/                 # Persistent intelligence layer
│   ├── store.py            # ChromaDB vector store (semantic search)
│   ├── embedder.py         # sentence-transformers all-MiniLM-L6-v2 embeddings
│   ├── extractor.py        # LLM-based fact extraction from session transcripts
│   └── manager.py          # High-level memory interface for the rest of XIA
│
├── skills/                 # Learned capabilities layer
│   ├── schema.py           # Skill data type definition
│   ├── store.py            # JSON file store + index
│   ├── extractor.py        # Auto-extract skills from successful agent results
│   └── manager.py          # Retrieve + inject skills into system prompts
│
├── interface/              # Terminal UI layer
│   ├── cli.py              # Main interactive loop + all /commands
│   ├── renderer.py         # Rich-based output (steps, answers, tables, banners)
│   └── theme.py            # Colours, icons, Rich styles
│
├── models/
│   └── model_config.yaml   # Model registry (model weights NOT stored here)
│
├── data/                   # Persistent data (git-ignored)
│   ├── conversations/      # Session transcripts saved as JSON
│   ├── embeddings/         # ChromaDB vector database files
│   └── skills_store/       # Extracted skills stored as JSON
│
├── workspace/              # Agent's working sandbox for user files
├── logs/                   # Rotating runtime logs
└── installers/             # Offline installer bundles (Python, Ollama, etc.)
```

---

## 🔧 Components In Detail

### 1. Core Layer (`core/`)

| File | Purpose |
|---|---|
| `llm.py` | Full Ollama HTTP client with streaming, non-streaming, JSON mode, automatic retry (tenacity), token tracking, model hot-swap, multi-turn history |
| `router.py` | Detects task type from keyword signals (coding, fast, smart, default) and picks the best available local model; supports temperature per profile |
| `prompt.py` | Assembles system prompts dynamically, injecting memory snippets and skill context |
| `config.py` | Loads and validates `config.yaml` into typed Python objects |
| `paths.py` | Resolves all paths relative to the SSD root — works on any drive letter |
| `health.py` | Checks Ollama connectivity, model availability, disk space, RAM at startup |
| `host.py` | Detects NVIDIA GPU (CUDA), VRAM, CPU cores, and available RAM for model selection |
| `logger.py` | Rotating log files with console output, structured for debugging |
| `errors.py` | Custom exception hierarchy (LLMError, ToolError, ConfigError, etc.) |

---

### 2. Agent Layer (`agent/`)

| File | Purpose |
|---|---|
| `agent.py` | The core reasoning engine. Runs the THINK→PLAN→ACT→OBSERVE loop. Manages tool calls, history, step emission, skill extraction after success |
| `session.py` | Routes messages to either direct chat mode (simple questions) or agent mode (complex tasks needing tools). Manages session lifecycle and auto-saves |
| `base.py` | Defines all data types: `AgentStep`, `AgentResult`, `AgentDecision`, `ToolCall`, `ToolResult`, `StepType`, `StepStatus` |

**Agent decision flow:**
- LLM is called with JSON mode on every iteration
- Response parsed into `AgentDecision` (thought, plan, tool call OR final_answer)
- If `is_done` → emit final answer, extract skill, return result
- If `has_tool_call` → execute tool, observe result, loop
- If neither → prompt model to conclude

---

### 3. Tool System (`tools/`)

XIA's tools are the agent's hands — they allow it to interact with the real world.

| Tool | Description |
|---|---|
| **filesystem** | Read, write, append, list directory, delete files. All operations are sandboxed to configured `allowed_paths`. Prevents path traversal attacks. |
| **terminal** | Execute shell commands with configurable timeout. Dangerous commands (rm, del, format, rmdir) require confirmation. Returns stdout + stderr. |
| **search** | Multi-provider web search. Tries Tavily → SerpAPI → DuckDuckGo in fallback order. Returns result titles, URLs, and snippets. |
| **fetch** | Fetches full text content from any URL using httpx. HTML is converted to clean text. Useful for reading documentation, articles, etc. |
| **browser** | Playwright-based Chrome automation. Supports: navigate, click, type, extract_text, get_title, get_url, wait, evaluate JavaScript, scroll, screenshot. |

**Tool Registry** (`tools/registry.py`):
- Tools are registered by name
- Fuzzy name matching handles model spelling variations
- `describe_all()` returns human-readable capability list for the system prompt
- `schemas_as_prompt()` injects JSON schemas into the agent prompt for structured calls

---

### 4. Memory System (`memory/`)

XIA has true persistent memory that survives across restarts and sessions.

| Component | Description |
|---|---|
| `store.py` | ChromaDB vector store. Each memory is embedded and stored. Queried semantically using cosine similarity. |
| `embedder.py` | Uses `sentence-transformers` model `all-MiniLM-L6-v2` (~90 MB) to convert text to vectors locally |
| `extractor.py` | Uses the LLM to extract high-quality facts from session transcripts (e.g., user preferences, project names, stated goals) |
| `manager.py` | Unified memory interface. Handles: retrieve (semantic), remember, remember_batch, save_session (auto-extract), recent, clear, count |

**How memory works:**
1. Before each agent run → top-K relevant memories retrieved and injected into system prompt
2. During sessions → user messages with factual signals (e.g., "my name is", "I prefer") are flagged
3. At session end → `save_session()` extracts both raw facts and LLM-distilled facts; stores all in ChromaDB
4. Similarity threshold: 0.40 (configurable). Max results per query: 5

---

### 5. Skill System (`skills/`)

XIA learns from experience. After every successful agent task, it auto-extracts a reusable skill.

| Component | Description |
|---|---|
| `schema.py` | `Skill` datatype: name, description, trigger_phrases, steps, tools_used, template, examples, usage_count |
| `store.py` | JSON file-based store with an in-memory index. Supports find_matching, save, delete, increment_usage |
| `extractor.py` | Uses the LLM to analyze successful `AgentResult` objects and produce a structured skill |
| `manager.py` | Retrieves relevant skills by query, injects them as context into the system prompt: "Relevant skills from past experience:" |

**Skill lifecycle:**
1. Agent completes a task successfully (with tool calls)
2. `SkillManager.process_result()` is triggered automatically
3. If no similar skill exists → LLM extracts a reusable skill and saves it
4. If a similar skill exists → its usage count is incremented
5. Future similar tasks get the skill injected as a hint, improving performance
6. Max stored skills: 500 (configurable)

---

### 6. Model Router (`core/router.py`)

XIA automatically picks the best available local model for each task:

| Profile | Best For | Preferred Models | Temperature |
|---|---|---|---|
| `coding` | Code, debugging, and algorithm-heavy tasks | qwen2.5-coder, deepseek-coder, codellama | 0.2 |
| `fast` | Quick questions, definitions, translations | phi4, phi3, gemma2:2b, qwen3.5:4b | 0.7 |
| `smart` | Deep reasoning, architecture, analysis | deepseek-r1, llama3.1, qwen2.5:14b | 0.7 |
| `default` | General-purpose conversation | mistral, llama3, llama3.2, gemma2 | 0.7 |

**Routing logic:**
- Task text is scored against keyword signal lists (e.g., "code", "function", "debug" → coding)
- Coding signals are weighted 3x; smart signals 2x; fast signals 1x
- Available models are queried from Ollama at runtime
- Best match from the preferred list is selected; falls back gracefully to default

---

### 7. CLI Interface (`interface/`)

XIA runs as a rich terminal application powered by the `rich` library.

| Component | Description |
|---|---|
| `cli.py` | Main interactive loop. Handles /commands, message routing, startup, shutdown |
| `renderer.py` | All visual output — banners, step panels, answer boxes, tables, colour-coded steps |
| `theme.py` | Custom Rich theme — colours, icons, styles for THINK/PLAN/ACT/OBSERVE/FINAL steps |

**At startup the CLI:**
1. Connects to Ollama and validates the model
2. Loads the tool registry
3. Initializes memory (ChromaDB)
4. Initializes skill manager
5. Detects available models and sets up the router
6. Displays a startup banner with memory count, skill count, active model

**At shutdown:**
- Auto-saves the session to `data/conversations/`
- Emits a "goodbye" message

---

### 8. CLI Commands

| Command | Description |
|---|---|
| `/memory` | Show stored memories (recent 8) |
| `/remember <fact>` | Manually store a fact in memory |
| `/forget` | Clear ALL memories (with confirmation) |
| `/skills` | List all learned skills |
| `/tools` | List all available tools with descriptions |
| `/models` | Show all downloaded Ollama models with routing profile |
| `/model <name>` | Hot-swap to a specific model immediately |
| `/set_default_model <name>` | Permanently set the default model in config.yaml |
| `/profile <name>` | Switch routing profile: coding / fast / smart / default |
| `/save` | Save current session to disk now |
| `/clear` | Clear conversation history (memory preserved) |
| `/history` | Show message count for this session |
| `/end` | Shut down XIA AND kill all Ollama processes |
| `/exit` / `/quit` / `/q` | Exit XIA gracefully |
| `/help` | Show all commands |

---

## 🤖 Multi-Model Support

XIA is model-agnostic. Pull any Ollama-compatible model and it will be detected and used:

```bash
ollama pull mistral          # default
ollama pull qwen2.5-coder    # best coding
ollama pull deepseek-r1      # best reasoning
ollama pull phi4             # fastest responses
ollama pull llama3.1         # smart + capable
```

The router automatically uses whatever is installed. No configuration changes needed.

---

## 🖥️ System Requirements

| | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 | Windows 11 |
| RAM | 8 GB | 16 GB+ |
| SSD Free Space | 30 GB | 60 GB+ |
| SSD Interface | USB 3.0 | USB 3.1 / NVMe |
| GPU | — (CPU works) | Any NVIDIA with CUDA |
| Python | 3.11+ | 3.12 |

---

## ⚙️ Configuration (`config.yaml`)

XIA is fully configurable through a single YAML file:

```
llm:       - provider, model, base_url, temperature, max_tokens, stream, timeout
agent:     - name, max_steps (10), max_retries (3), verbose
memory:    - enabled, provider (chromadb), collection_name, embedding model,
             max_results (5), similarity_threshold (0.40)
skills:    - enabled, auto_extract, max_skills (500)
tools:     - filesystem allowed_paths, terminal timeout + dangerous commands blocklist,
             search provider + max_results
interface: - type (cli), theme (dark), show_thinking, show_tool_calls
logging:   - level (INFO), log_to_file, max_log_size_mb (10), backup_count (3)
```

---

## 🔐 Security Features

- **Sandboxed file access** — only allowed paths in config can be accessed
- **Command blocklist** — dangerous shell commands (rm, del, format, rmdir) require explicit confirmation
- **Command timeout** — shell commands killed after 600 seconds
- **Local-only** — no data ever leaves the machine (no cloud LLM APIs)
- **Path traversal protection** — filesystem tool validates all paths

---

## 🛠️ Build History

| Part | What Was Built |
|---|---|
| 1 | Project scaffold, SSD layout, config system, drive-agnostic path resolution |
| 2 | Self-bootstrapping Windows launcher (venv, deps, Ollama install, model pull) |
| 3 | Ollama LLM client — streaming, history, JSON mode, model hot-swap |
| 4 | Agentic loop — THINK→PLAN→ACT→OBSERVE, session routing |
| 5 | Tool system — filesystem, terminal, tool registry, sandboxed execution |
| 6 | Web search (Tavily/DuckDuckGo) + full-page text fetcher |
| 7 | Persistent memory — ChromaDB, sentence-transformers, semantic retrieval |
| 8 | Skill system — auto-extraction, JSON store, prompt injection |
| 9 | Rich terminal UI — coloured step panels, markdown output, all /commands |
| 10 | Robustness — health checks, GPU detection, structured error types |
| 11 | Browser automation (Playwright) |
| +  | Multi-model routing — auto-pick model per task, /profile command |

---

## 🚀 What Makes XIA Different

| Feature | Typical AI Tool | XIA |
|---|---|---|
| Setup | Manual, complex | One-click, self-bootstraps |
| Memory | Temporary (per session) | Persistent (ChromaDB, survives reboots) |
| Real-world actions | Limited | Files, shell, browser, web search |
| Learning | None | Skill extraction + reuse |
| Portability | Host-dependent | Runs from any SSD, any PC |
| Multi-model | Rare / manual | Built-in auto-routing |
| Privacy | Cloud-based | Fully local, 100% offline |

---

## 🚀 Quick Start

```bash
# 1. Plug in your SSD
# 2. Double-click launch.bat
# 3. That's it — XIA handles everything else

# Optional: add API keys for web search
cp .env.example .env
# Edit .env and add TAVILY_API_KEY or SERPAPI_KEY

# Optional: install browser support
.venv\Scripts\python install_browser.py
```

---

## 📄 Dependencies (Key Libraries)

| Library | Purpose |
|---|---|
| `httpx` | HTTP client for Ollama API calls |
| `tenacity` | Automatic retry with exponential backoff |
| `chromadb` | Local vector database for memory |
| `sentence-transformers` | Local text embeddings (all-MiniLM-L6-v2) |
| `rich` | Beautiful terminal UI, panels, tables |
| `playwright` | Chrome browser automation |
| `pyyaml` | Config file parsing |

---

## 💡 Summary

> XIA is a **portable, offline, self-learning AI agent** — not just a chatbot.
> It reasons autonomously, uses real-world tools, remembers you across sessions,
> extracts knowledge from its own experience, and runs privately on your hardware.
> Plug it in anywhere. It's ready in seconds.

---

*Generated: 2026-03-31 | Version: 1.0 | License: MIT*

