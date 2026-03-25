"""
launch.py — xia Bootstrap Controller (Part 10: Hardened)

Runs every time xia starts. Each step is idempotent.
Now includes host detection, health checks, and Ollama GPU optimisation.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"

def ok(msg):    print(f"  {C.GREEN}✓{C.RESET}  {msg}")
def info(msg):  print(f"  {C.CYAN}→{C.RESET}  {msg}")
def warn(msg):  print(f"  {C.YELLOW}!{C.RESET}  {msg}")
def err(msg):   print(f"  {C.RED}✗{C.RESET}  {msg}")
def step(msg):  print(f"\n  {C.BOLD}{msg}{C.RESET}")


def find_xia_root() -> Path:
    if env_root := os.environ.get("XIA_ROOT"):
        return Path(env_root).resolve()
    current = Path(__file__).resolve().parent
    for candidate in [current, current.parent]:
        if (candidate / "config.yaml").exists():
            return candidate
    return Path(__file__).resolve().parent


ROOT        = find_xia_root()
VENV_DIR    = ROOT / ".venv"
VENV_PY     = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP    = VENV_DIR / "Scripts" / "pip.exe"
REQ_FILE    = ROOT / "requirements.txt"
MAIN_PY     = ROOT / "main.py"
STAMP       = VENV_DIR / ".install_stamp"
OLLAMA_URL  = "https://ollama.com/download/OllamaSetup.exe"


def req_hash() -> str:
    import hashlib
    if not REQ_FILE.exists():
        return ""
    return hashlib.md5(REQ_FILE.read_bytes()).hexdigest()


def read_config(key_path: str, default=None):
    try:
        import yaml
        with open(ROOT / "config.yaml", "r") as f:
            data = yaml.safe_load(f)
        for k in key_path.split("."):
            data = data.get(k, {})
        return data if data != {} else default
    except Exception:
        return default


# ── Step 1: Venv ───────────────────────────────────────────────────────────────

def ensure_venv():
    step("Step 1 — Virtual environment")

    if VENV_PY.exists():
        # Validate the venv actually works on THIS machine.
        # A venv carries absolute paths to the Python that built it — so a
        # venv created on PC-A will silently fail on PC-B even if the .exe
        # file exists on the SSD.
        probe = subprocess.run(
            [str(VENV_PY), "--version"],
            capture_output=True, text=True,
        )
        if probe.returncode == 0:
            ok(f"venv OK  ({probe.stdout.strip()})")
            return

        warn("Venv is stale (was built on a different machine). Rebuilding...")
        import shutil
        shutil.rmtree(str(VENV_DIR), ignore_errors=True)

    info("Creating virtual environment (first time on this machine)...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0:
        err("Failed to create virtual environment.")
        sys.exit(1)
    ok("Virtual environment created.")


# ── Step 2: Dependencies ───────────────────────────────────────────────────────

def ensure_dependencies():
    step("Step 2 — Python dependencies")
    if not REQ_FILE.exists():
        warn("requirements.txt not found — skipping.")
        return

    current = req_hash()
    if STAMP.exists() and STAMP.read_text().strip() == current:
        ok("Dependencies up to date.")
        return

    info("Installing dependencies (this may take a few minutes the first time)...")
    print()  # blank line before pip output
    result = subprocess.run([
        str(VENV_PY), "-m", "pip", "install",
        "-r", str(REQ_FILE),
        "--progress-bar", "on",
        "--disable-pip-version-check",
    ])
    print()  # blank line after pip output

    if result.returncode != 0:
        err("Dependency install failed.")
        err(f'Try manually: "{VENV_PY}" -m pip install -r "{REQ_FILE}"')
        sys.exit(1)

    STAMP.write_text(current)
    ok("Dependencies installed.")


# ── Step 3: Host detection ─────────────────────────────────────────────────────

def detect_host() -> dict:
    step("Step 3 — Host detection")
    host = {"cpu_cores": os.cpu_count() or 1, "ram_gb": 8.0, "has_gpu": False}

    # RAM
    try:
        result = subprocess.run(
            ["wmic", "OS", "get", "TotalVisibleMemorySize", "/value"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "TotalVisibleMemorySize=" in line:
                kb = int(line.split("=")[1].strip())
                host["ram_gb"] = round(kb / (1024 ** 2), 1)
    except Exception:
        pass

    # GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            host["has_gpu"] = True
            host["gpu_name"] = result.stdout.strip().splitlines()[0]
    except Exception:
        pass

    gpu_str = host.get("gpu_name", "CPU only") if host["has_gpu"] else "CPU only"
    ok(f"{host['ram_gb']}GB RAM  ·  {host['cpu_cores']} cores  ·  {gpu_str}")

    # Set Ollama env vars based on host
    threads = max(1, host["cpu_cores"] - 2)
    os.environ["OLLAMA_NUM_THREADS"] = str(threads)
    if host["has_gpu"]:
        os.environ["OLLAMA_GPU_LAYERS"] = "999"
        info(f"GPU detected — enabling GPU acceleration")

    return host


# ── Step 4: Ollama ─────────────────────────────────────────────────────────────

def server_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_ollama():
    step("Step 4 — Ollama")

    if not shutil.which("ollama"):
        print()
        warn("Ollama not found on this machine.")
        answer = input("  Install Ollama now? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            err("Ollama is required. Install from https://ollama.com")
            sys.exit(1)
        _install_ollama()
    else:
        ok("Ollama installed.")

    if not server_running():
        info("Starting Ollama server...")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for i in range(20):
            time.sleep(1)
            if server_running():
                ok("Ollama server started.")
                break
            print(f"\r  Waiting... {i+1}s", end="", flush=True)
        else:
            print()
            warn("Ollama slow to start — xia will retry on first request.")
    else:
        ok("Ollama server running.")

    # Pull model if needed
    model = read_config("llm.model", "mistral")
    _ensure_model(model)


def _install_ollama():
    installer = Path(os.environ.get("TEMP", ROOT)) / "OllamaSetup.exe"
    info("Downloading Ollama installer...")
    try:
        urllib.request.urlretrieve(OLLAMA_URL, installer, _progress)
        print()
    except Exception as e:
        err(f"Download failed: {e}")
        sys.exit(1)
    info("Running installer (follow the prompts)...")
    subprocess.run([str(installer)])
    if shutil.which("ollama"):
        ok("Ollama installed.")
    else:
        warn("Ollama may need a terminal restart to appear in PATH.")


def _ensure_model(model: str):
    info(f"Checking model '{model}'...")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = json.loads(r.read())
            names = [m["name"].split(":")[0] for m in data.get("models", [])]
            if model in names:
                ok(f"Model '{model}' ready.")
                return
    except Exception:
        warn("Could not check models — server may still be starting.")
        return

    print()
    warn(f"Model '{model}' not downloaded yet (~4-5GB).")
    answer = input(f"  Download '{model}' now? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        warn(f"Skipping. Run manually: ollama pull {model}")
        return
    info(f"Pulling '{model}'...")
    subprocess.run(["ollama", "pull", model])
    ok(f"Model '{model}' ready.")


def _progress(count, block, total):
    if total > 0:
        pct = min(100, count * block * 100 // total)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}%", end="", flush=True)


# ── Step 5: Health check ───────────────────────────────────────────────────────

def run_health_check():
    step("Step 5 — Health check")
    try:
        sys.path.insert(0, str(ROOT))
        from core.health import HealthChecker
        checker = HealthChecker()
        ok_flag, issues = checker.run()
        errors   = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        if errors:
            checker.print_report(issues)
            sys.exit(1)
        if warnings:
            for w in warnings:
                warn(f"{w.check}: {w.message}")
        ok("Health check passed.")
    except Exception as e:
        warn(f"Health check skipped: {e}")


# ── Step 6: Launch ─────────────────────────────────────────────────────────────

def launch():
    step("Step 6 — Launching xia")
    if not MAIN_PY.exists():
        err(f"main.py not found: {MAIN_PY}")
        sys.exit(1)

    env = os.environ.copy()
    env["XIA_ROOT"] = str(ROOT)

    ok("Starting...\n")
    print("  " + "─" * 48)

    result = subprocess.run(
        [str(VENV_PY), str(MAIN_PY)],
        env=env,
        cwd=str(ROOT),
    )

    print("\n  " + "─" * 48)
    if result.returncode not in {0, 130}:  # 130 = Ctrl+C
        err(f"xia exited with code {result.returncode}")
        sys.exit(result.returncode)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        os.system("")

    print()
    print(f"  {'─'*48}")
    print(f"  {'xia  —  Bootstrap':^48}")
    print(f"  {'─'*48}")
    print(f"  root   : {ROOT}")
    print(f"  python : {sys.version.split()[0]}")
    print(f"  {'─'*48}")

    try:
        ensure_venv()
        ensure_dependencies()
        detect_host()
        ensure_ollama()
        run_health_check()
        launch()
    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
