#!/usr/bin/env bash
# run.sh - xia launcher for macOS / Linux
# Mirror of run.bat - always run from any directory, paths are relative to this script.

set -euo pipefail

# ── Locate root (always relative to this script, symlink-safe) ───────────────
XIA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Key paths ────────────────────────────────────────────────────────────────
XIA_VENV="$XIA_ROOT/.venv"
XIA_PYTHON="$XIA_VENV/bin/python"

# ── Portable storage paths (no host footprint) ────────────────────────────────
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export OLLAMA_MODELS="$XIA_ROOT/models/ollama"
export OLLAMA_HOME="$XIA_ROOT/models/ollama"
export PLAYWRIGHT_BROWSERS_PATH="$XIA_ROOT/models/playwright"
export HF_HOME="$XIA_ROOT/models/hf_home"
export PIP_NO_CACHE_DIR=1

# ── Helpers ───────────────────────────────────────────────────────────────────
red()    { printf '\033[91m%s\033[0m\n' "$*"; }
yellow() { printf '\033[93m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n'  "$*"; }

# ── FAST PATH: venv exists and core modules import cleanly ────────────────────
if [[ -x "$XIA_PYTHON" ]]; then
    if "$XIA_PYTHON" -c "import pip, dotenv, yaml, rich, ollama" &>/dev/null; then
        exec "$XIA_PYTHON" "$XIA_ROOT/launch.py"
    fi
fi

# ── SETUP MODE: venv missing, broken, or stale ───────────────────────────────
echo
echo "  xia  -  initial setup..."
echo

mkdir -p "$XIA_ROOT/models/ollama"

# ── Step 1: Find system Python ────────────────────────────────────────────────
echo "  *  checking host python..."

SYS_PYTHON=""

find_system_python() {
    # Explicit version binaries (most reliable)
    for cmd in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo "False")
            if [[ "$ver" == "True" ]]; then
                SYS_PYTHON="$(command -v "$cmd")"
                return 0
            fi
        fi
    done

    # macOS: Homebrew locations
    for brew_prefix in /opt/homebrew /usr/local; do
        for cmd in python3.13 python3.12 python3.11 python3; do
            candidate="$brew_prefix/bin/$cmd"
            if [[ -x "$candidate" ]]; then
                ver=$("$candidate" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo "False")
                if [[ "$ver" == "True" ]]; then
                    SYS_PYTHON="$candidate"
                    return 0
                fi
            fi
        done
    done

    return 1
}

if find_system_python; then
    echo "     - found system python: $SYS_PYTHON"
else
    echo "     - host python not found"
    echo
    red "  [ERROR] Python 3.11+ is required but was not found on this machine."
    echo "  Install Python from https://python.org (or via Homebrew: brew install python@3.11)"
    echo "  then re-run:  bash run.sh"
    echo
    exit 1
fi

# ── Step 2: Remove stale venv ─────────────────────────────────────────────────
if [[ -d "$XIA_VENV" ]]; then
    echo "  *  removing old virtual environment..."
    rm -rf "$XIA_VENV"
    if [[ -d "$XIA_VENV" ]]; then
        echo
        red "  [ERROR] Cannot delete old .venv - files may be locked."
        echo "  Close any processes using xia, then re-run run.sh"
        echo
        exit 1
    fi
fi

# ── Step 3: Build fresh venv ──────────────────────────────────────────────────
echo "  *  building virtual environment..."

if ! "$SYS_PYTHON" -m venv "$XIA_VENV"; then
    echo
    red "  [ERROR] Failed to create virtual environment."
    echo "  Check that $XIA_ROOT is writable, or try:  sudo bash run.sh"
    echo
    exit 1
fi

if ! "$XIA_PYTHON" -c "import sys" &>/dev/null; then
    echo
    red "  [ERROR] New venv is broken. Re-run run.sh to try again."
    echo
    exit 1
fi

# ── Step 4: Bootstrap pip ─────────────────────────────────────────────────────
echo "  *  bootstrapping pip..."

"$XIA_PYTHON" -m ensurepip --upgrade &>/dev/null || true
"$XIA_PYTHON" -m pip install --quiet --upgrade pip &>/dev/null || true

# ── Step 5: Hand off to launch.py ─────────────────────────────────────────────
echo "     - virtual environment ready"
echo

exec "$XIA_PYTHON" "$XIA_ROOT/launch.py"
