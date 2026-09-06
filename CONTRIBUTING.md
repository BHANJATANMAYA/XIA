# Contributing to XIA 🧬

Thank you for your interest in contributing to XIA! We are excited to build a private, self-evolving, and portable developer partner together. 

Please read this guide to understand how to get started, set up your development environment, and submit changes.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to the project maintainers.

---

## How Can I Contribute?

### 🐛 Reporting Bugs
- Search existing issues to see if the bug has already been reported.
- If not, open a new issue using the **Bug Report** template.
- Include detailed steps to reproduce, actual vs. expected behavior, and relevant logs from the `logs/` directory.

### 💡 Proposing Features
- Open a new issue using the **Feature Request** template.
- Explain the "why" and "how" of your proposal.
- For new tools or memory architectures, sketch out the API or interface design.

### 📝 Improving Documentation
- Documentation fixes (typos, clarifications, examples) can be submitted directly as Pull Requests.

### 💻 Submitting Code Changes
- Fork the repository and create a branch for your feature or bugfix: `git checkout -b feature/my-amazing-feature`.
- Write clean, documented code that follows the project structure.
- Verify your changes with the test suite (see below) before opening a Pull Request.

---

## Developer Environment Setup

XIA is self-bootstrapping, which makes setting up a development environment straightforward.

### 1. Prerequisites
- **Python**: version `3.11` or `3.12`
- **Ollama**: Installed and running locally ([Download Ollama](https://ollama.com))
- **Git**: Installed on your system

### 2. Setup Repository
Clone the repository and enter the directory:
```bash
git clone https://github.com/yourusername/xia.git
cd xia
```

### 3. Let the Bootstrapper Initialize
Instead of manually creating virtual environments and installing packages, run the bootstrapper:
- **Windows**: Run `run.bat` or `.venv\Scripts\python launch.py`
- **macOS/Linux**: Run `bash run.sh`

The bootstrapper will automatically:
1. Create a virtual environment under `.venv/`
2. Install Python packages listed in `requirements.txt`
3. Detect host CPU cores, RAM, and GPU support
4. Validate Ollama connectivity and pull the default model (e.g., `mistral`)
5. Run a startup health check

### 4. Install Browser Tool Dependencies (Optional)
If you are developing or testing browser-based tools, run the Playwright browser installer:
```bash
# Windows
.venv\Scripts\python scripts/install_browser.py

# macOS/Linux
.venv/bin/python scripts/install_browser.py
```

---

## Code Style & Conventions

- **PEP 8**: Follow standard Python style guidelines.
- **Typing**: Use type hints for function signatures and data models where possible.
- **Portability**: Do NOT use absolute paths. Always use path properties from the global `PATHS` object in `src/core/paths.py`.
- **Privacy-First**: Never introduce dependencies or tools that make telemetry calls or send user prompts/code to third-party cloud services without explicit configuration and user consent.

---

## Verifying & Testing

XIA has minimal testing scripts inside the `tests/` directory. Before committing, run these scripts to ensure no core regressions occurred:

```bash
# Run identity and conversational tests
python tests/test_identity.py

# Run minimal client tests
python tests/test_minimal.py
```

Make sure all tests pass cleanly without errors.

---

## Pull Request Checklist

Before submitting a Pull Request, ensure that:
1. All linting and basic checks pass.
2. The virtual environment setup (`launch.py`) still boots cleanly.
3. No secrets, credentials, API keys, or personal paths are hardcoded or committed (verify with `git diff`).
4. New features are adequately documented in `README.md` or the `docs/` folder.
5. Your commit messages are clear and describe the changes made (e.g., `feat: load soul prompt dynamically from SOUL.md`).
