# xia — Offline Deployment Guide

How to prepare xia for fully air-gapped deployment — no internet required
on any target machine.

---

## Concept

The `installers\` folder on your SSD acts as a local package cache.
The first time you run `run.bat` on a machine with internet, it downloads
Python and Ollama and saves them there. Every machine after that uses the
cached files — zero internet required.

```
xia\
  installers\
    python-3.12.4-amd64.exe    ← cached after first run
    OllamaSetup.exe            ← cached after first run
  models\
    ollama\                    ← model weights (already on your SSD)
```

---

## Option A — Automatic caching (easiest)

1. Run `run.bat` once on any machine with internet
2. It downloads and installs everything, saving installers to `installers\`
3. Eject the SSD
4. On any other machine — plug in and run `run.bat`
5. No internet needed. Everything installs from the SSD.

---

## Option B — Manual pre-download (for truly air-gapped environments)

Download these files manually and place them in `D:\xia\installers\`:

| File | URL | Size |
|---|---|---|
| `python-3.12.4-amd64.exe` | https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe | ~25MB |
| `OllamaSetup.exe` | https://ollama.com/download/OllamaSetup.exe | ~50MB |

After placing the files:
```
D:\xia\installers\python-3.12.4-amd64.exe   ← must be exact filename
D:\xia\installers\OllamaSetup.exe            ← must be exact filename
```

Run `run.bat` — no internet will be used.

---

## What the launcher does (step by step)

```
[1/6] Checking Python
      → Tests venv\Scripts\python.exe first (fastest)
      → If stale (different machine) → rebuilds automatically
      → If missing → searches system, then installs

[2/6] Installing Python (if needed)
      → Checks installers\python-3.12.4-amd64.exe FIRST
      → Falls back to internet only if file is missing
      → Saved to installers\ for future use

[3/6] Checking Python dependencies
      → Installs requirements.txt into venv
      → Skips if already up to date (timestamp check)

[4/6] Checking Ollama
      → Checks installers\OllamaSetup.exe FIRST
      → Falls back to internet only if file is missing
      → Saved to installers\ for future use

[5/6] Starting Ollama server
      → Kills existing instance (ensures fresh env vars)
      → Starts in background
      → Waits up to 20 seconds for port 11434

[6/6] Launching xia
      → Runs launch.py inside the venv
      → Shows exit code and log path on failure
```

---

## Offline error messages

If the launcher can't install something and has no internet, it shows:

```
[OFFLINE] Cannot install Python automatically.

Option A - Copy installer to SSD (Recommended):
  1. On a machine with internet, download:
     https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe
  2. Place it here:
     D:\xia\installers\python-3.12.4-amd64.exe
  3. Re-run run.bat
```

It will never silently fail — always tells you exactly what to do.

---

## What gets installed where

| Component | Location | Persists on SSD? |
|---|---|---|
| Python | Host machine (per-user, no admin) | No — per machine |
| Virtual environment (.venv) | `D:\xia\.venv\` | Yes |
| Python packages | `D:\xia\.venv\` | Yes |
| Ollama binary | Host machine | No — per machine |
| Ollama models | `D:\xia\models\ollama\` | Yes |
| xia memories | `D:\xia\data\embeddings\` | Yes |
| xia skills | `D:\xia\data\skills_store\` | Yes |

Python and Ollama binaries install to the host machine (required for system integration),
but the venv, models, memories, and skills all live on the SSD and travel with you.

---

## Updating Python version

To use a different Python version:
1. Download the new installer to `installers\python-X.X.X-amd64.exe`
2. Update the filename reference in `run.bat` line: `set "XIA_PY_INSTALLER=..."`
3. Delete `.venv` folder — it will rebuild with the new Python
4. Run `run.bat`
