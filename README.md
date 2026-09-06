

<p align="center">
  <img src="docs/assets/logo_text.png" alt="xia logo" width="500">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12-brightgreen.svg" alt="Python Support">
  <img src="https://img.shields.io/badge/Ollama-Local-orange.svg" alt="Ollama Local">
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen.svg" alt="PRs Welcome">
</p>

XIA is a **private, self-evolving AI brain** that lives entirely on your SSD. It is portable, fast, local-first, and built to act as your ultimate developer teammate. 

By utilizing local LLMs (via Ollama) and a local vector database (ChromaDB), XIA performs tasks, executes terminal commands, automates web browsing, and remembers your preferences—all **100% offline**, without ever sending your data to the cloud.

---

## 🎯 Core Values

*   **🔒 Private**: Complete data ownership. No cloud APIs, telemetry, or remote trackers.
*   **💾 Portable**: Lives entirely inside your SSD layout. Plug it into any machine, click and run.
*   **⚡ Fast**: Integrated RAM cache and working memory minimize unnecessary vector lookups.
*   **🧬 Self-Evolving**: Learns from every conversation and extracts procedural skills over time.

---

## 🏗️ How It Works

XIA is built on a modular reasoning loop and persistent intelligence layer:

```
                  User Prompt
                       │
                       ▼
                 CLI Interface
                       │
                       ▼
                 Agent Core Loop
                       │
      ┌────────────────┼────────────────┐
      ▼                ▼                ▼
 Layered Memory   Tool Registry   Self-Evolution
 (ChromaDB/RAM)  (Terminal/Browser) (Skill Store)
```

### 1. The Reasoning Loop
XIA follows an autonomous **THINK ➔ PLAN ➔ ACT ➔ OBSERVE** loop:
1.  **THINK**: Evaluates what tool is needed based on your request.
2.  **PLAN**: Lays out a multi-step plan on the first step.
3.  **ACT**: Invokes the selected tool with structured parameters.
4.  **OBSERVE**: Inspects the tool's result, updates state, and continues until a final answer is produced.

#### Loop Detection & Progress Tracking
- **Action-to-Tool Mapping**: Automatically maps common action names (e.g., `write`, `read`, `create`) to the correct tool and action combination, preventing tool name mismatches.
- **Loop Detection**: Tracks recent actions and detects when the agent repeats the same action, providing guidance to try a different approach.
- **Progress Tracking**: Monitors accomplishments (files created, commands executed) and includes this context in prompts to help the agent recognize task completion.

### 2. Layered Memory System
Memory is divided into layers for fast retrieval and deep contextual awareness:
-   **Working Memory**: RAM cache containing recent interaction context.
-   **Semantic Recall**: ChromaDB vector store matching long-term memories locally.
-   **Relationship Graph**: A local relationship graph matching connected recall concepts.
-   **Re-ranking**: Retrieves vector candidates and ranks them by relevance, recency, and importance.

### 3. Self-Evolution (Skills)
After every successful complex task, XIA uses an **automatic skill extraction loop**. It distills the steps, triggers, and tool recipes into a reusable skill file (stored under `data/skills_store/`). Future matching requests retrieve these skills, bypassing trial-and-error reasoning.

---

## 🎨 Customizing the Soul (`SOUL.md`)

Unlike traditional agents where system prompts are baked into code, **XIA's identity is completely modular**. 

The root directory contains a [SOUL.md](SOUL.md) file. You can open and edit this file in markdown to customize:
*   **Chat Soul**: Personality guidelines, tone, relationship constraints, and few-shot conversation examples.
*   **Agent Soul**: Specialized instructions for tool execution and JSON formatting constraints.

The prompt builder (`src/core/prompt.py`) parses this file dynamically, applying personality changes on the next message without needing to restart the agent.

---

## 🚀 Quick Start

### 1. Bootstrapping
XIA is completely self-contained. Clone the repository and run the bootstrapper:
-   **Windows**: Double-click [run.bat](run.bat) (or run `python launch.py` in PowerShell)
-   **macOS / Linux**: Run `bash run.sh`

The bootstrapper will automatically create a virtual environment (`.venv/`), install dependency packages, search for GPU support, start the local Ollama daemon, and download the default model weights.

### Voice Control
After startup, type `/voice` and speak a request. Use `/voice on` for continuous hands-free requests, `/voice devices` to list microphones, and `/voice speak on` for local spoken replies. Audio is transcribed locally; the Whisper model is downloaded once into `models/whisper` on first use. Configure the model, microphone, confirmation prompt, and speech settings in `config.yaml`.

### 2. Optional: Add Browser Support
To allow XIA to browse the web, click links, and summarize pages using Playwright, run the browser installer:
```bash
# Windows
.venv\Scripts\python scripts/install_browser.py

# macOS/Linux
.venv/bin/python scripts/install_browser.py
```

### 3. Optional: Add Search API Keys
XIA works out of the box with DuckDuckGo (free, no keys). For more advanced search queries, copy `.env.example` to `.env` and fill in your Tavily or SerpAPI credentials:
```bash
cp .env.example .env
```

---

## 🛠️ Tool Capabilities

*   📁 **Filesystem**: Sandboxed file operations (read, write, append, delete, list) protected against traversal attacks.
*   💻 **Terminal**: System command executor with dangerous command guards (requires confirmation for `rm`, `del`, `format`, `rmdir`).
*   🌐 **Search**: Web queries utilizing Tavily, SerpAPI, or DuckDuckGo.
*   📄 **Fetch**: Extracts and converts raw web pages and articles to clean markdown text.
*   👁️ **Browser**: Playwright-controlled headless Chromium instance to click, scroll, fill forms, and scrape data.

### Smart Tool Routing
XIA includes intelligent action-to-tool mapping that automatically resolves common action names to the correct tool:
- `write`, `create` → Filesystem (write action)
- `read` → Filesystem (read action)
- `delete`, `remove` → Filesystem (delete action)
- `list`, `ls` → Filesystem (list action)
- `run`, `execute`, `exec`, `shell` → Terminal
- `search`, `find` → Search tool
- `browse`, `open` → Browser tool
- `fetch`, `get`, `download` → Fetch tool

---

## 💬 Command Console

During active terminal sessions, use the following commands:
*   `/help` - Show available console commands.
*   `/memory` - Inspect recent long-term memory entries.
*   `/remember <fact>` - Manually inject a fact into ChromaDB.
*   `/forget` - Clear stored memories.
*   `/skills` - List all self-evolved skills.
*   `/tools` - List registered agent tools.
*   `/models` - View downloaded models and active routing profiles.
*   `/model <name>` or `/use_model <name>` - Swap the current LLM model on the fly.
*   `/set_default_model <name>` - Set the default model in config.yaml permanently.
*   `/profile <name>` - Switch routing profile (`coding` / `fast` / `smart` / `default`).
*   `/history` - Show message count for current session.
*   `/lessons` - Show lessons learned from past tasks.
*   `/preferences` - Show learned user preferences.
*   `/reflect` - Reflect on the last agent task (success, steps, tools used).
*   `/save` - Persist the current session conversation log.
*   `/clear` - Clear the CLI chat screen history.
*   `/exit` or `/quit` - Close the agent session cleanly.
*   `/end` - Shut down xia AND forcefully stop ALL ollama processes.

---

## 🤝 Contributing & Community

Contributions are what make the open-source community amazing! 

*   Review our [Contributing Guidelines](CONTRIBUTING.md) to set up your dev workspace and learn the pull request workflow.
*   Read our [Code of Conduct](CODE_OF_CONDUCT.md) to understand community standards.
*   For security concerns, read [SECURITY.md](SECURITY.md) to report vulnerabilities privately.

---

## 📄 License

XIA is licensed under the [MIT License](LICENSE) — feel free to modify, extend, and distribute.
