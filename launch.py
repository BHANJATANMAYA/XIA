"""
launch.py - xia Bootstrap Controller (Part 10: Hardened)

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
    DIM    = "\033[2m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    PURPLE = "\033[95m"


_had_sub = False


def start_step(label: str):
    global _had_sub
    _had_sub = False
    print(f"  {C.PURPLE}*{C.RESET}  {C.DIM}{label:<26}{C.RESET} [{C.CYAN}...{C.RESET}]", end="", flush=True)


def end_step(label: str, status: str, style=C.GREEN, sub_msg: str = ""):
    global _had_sub
    if _had_sub:
        print(f"  {C.PURPLE}*{C.RESET}  {C.DIM}{label:<26}{C.RESET} [{style}{status}{C.RESET}]", flush=True)
    else:
        # Pad with spaces to clear any pending spinner text on the same line
        print(f"\r  {C.PURPLE}*{C.RESET}  {C.DIM}{label:<26}{C.RESET} [{style}{status}{C.RESET}]" + " " * 30, flush=True)
    if sub_msg:
        print(f"     {C.DIM}- {sub_msg}{C.RESET}", flush=True)


def print_sub(msg: str, style=C.DIM):
    global _had_sub
    if not _had_sub:
        print() # print a newline first
        _had_sub = True
    print(f"     {style}- {msg}{C.RESET}", flush=True)


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
if sys.platform == "win32":
    VENV_PY = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PY = VENV_DIR / "bin" / "python"
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


# -- Step 1: Venv ---------------------------------------------------------------

def ensure_venv():
    start_step("environment")

    if VENV_PY.exists():
        # Validate the venv binary works on THIS machine.
        probe = subprocess.run(
            [str(VENV_PY), "-c", "import sys"],
            capture_output=True, text=True,
        )
        if probe.returncode == 0:
            end_step("environment", "ok")
            return

        print_sub("stale/broken virtual environment detected.", C.YELLOW)
        # If we ARE the venv python we can't delete ourselves.
        if Path(sys.executable).resolve() == VENV_PY.resolve():
            launcher = "run.bat" if sys.platform == "win32" else "run.sh"
            print_sub(f"Please run {launcher} to automatically rebuild the environment.", C.RED)
            sys.exit(1)

        import shutil
        shutil.rmtree(str(VENV_DIR), ignore_errors=True)
        if STAMP.exists():
            try:
                STAMP.unlink()
            except Exception:
                pass

        if VENV_DIR.exists():
            print_sub("Cannot delete old .venv (files are locked). Close all xia windows and re-run.", C.RED)
            sys.exit(1)

    print_sub("creating virtual environment...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0:
        end_step("environment", "failed", C.RED)
        print_sub(f"venv creation failed. Try running as administrator or check disk space.", C.RED)
        sys.exit(1)

    # Bootstrap pip using ensurepip (avoids network/certifi issues)
    subprocess.run([str(VENV_PY), "-m", "ensurepip", "--upgrade"], capture_output=True)
    end_step("environment", "created")


# -- Step 2: Dependencies -------------------------------------------------------

def ensure_dependencies():
    start_step("dependencies")
    if not REQ_FILE.exists():
        end_step("dependencies", "missing", C.YELLOW)
        return

    # Check if already installed
    probe = subprocess.run(
        [str(VENV_PY), "-c", "import dotenv, yaml, rich, ollama"],
        capture_output=True, text=True,
    )
    current = req_hash()
    if probe.returncode == 0 and STAMP.exists() and STAMP.read_text().strip() == current:
        end_step("dependencies", "ok")
        return

    import tempfile
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as temp_err:
        process = subprocess.Popen(
            [str(VENV_PY), "-m", "pip", "install",
                "-r", str(REQ_FILE),
                "--upgrade",
                "--disable-pip-version-check",
                "--quiet",
            ],
            stdout=subprocess.DEVNULL, stderr=temp_err
        )

        spinner = ["|", "/", "-", "\\"]
        i = 0
        while process.poll() is None:
            print(f"\r  {C.PURPLE}*{C.RESET}  {C.DIM}{'dependencies':<26}{C.RESET} [{C.CYAN}{spinner[i % len(spinner)]}{C.RESET}] installing...", end="", flush=True)
            i += 1
            time.sleep(0.1)

        if process.returncode != 0:
            print(f"\r  {C.PURPLE}*{C.RESET}  {C.DIM}{'dependencies':<26}{C.RESET} [{C.RED}failed{C.RESET}]" + " " * 20, flush=True)
            temp_err.seek(0)
            stderr_data = temp_err.read()
            if stderr_data.strip():
                print(f"\n{C.RED}Pip Error:{C.RESET}\n{stderr_data.strip()}")
            sys.exit(1)

    STAMP.write_text(current)
    end_step("dependencies", "updated")


# -- Step 3: Host detection -----------------------------------------------------

HOST_CACHE = ROOT / "data" / ".host_cache.json"


def _load_host_cache() -> dict | None:
    try:
        if HOST_CACHE.exists():
            import platform
            data = json.loads(HOST_CACHE.read_text(encoding="utf-8"))
            if data.get("hostname") == platform.node():
                return data
    except Exception:
        pass
    return None


def _save_host_cache(host: dict):
    try:
        import platform
        host["hostname"] = platform.node()
        HOST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        HOST_CACHE.write_text(json.dumps(host, indent=2), encoding="utf-8")
    except Exception:
        pass


def detect_host() -> dict:
    start_step("host system")

    cached = _load_host_cache()
    if cached:
        gpu_str = cached.get("gpu_name", "CPU only") if cached.get("has_gpu") else "CPU only"
        status = "gpu" if cached.get("has_gpu") else "cpu"
        end_step("host system", status, sub_msg=f"{cached['ram_gb']}GB RAM  |  {cached['cpu_cores']} cores  |  {gpu_str}")
        _apply_host_env(cached)
        return cached

    host: dict = {"cpu_cores": os.cpu_count() or 1, "ram_gb": 8.0, "has_gpu": False, "gpu_name": "CPU only"}

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
    status = "gpu" if host["has_gpu"] else "cpu"
    end_step("host system", status, sub_msg=f"{host['ram_gb']}GB RAM  |  {host['cpu_cores']} cores  |  {gpu_str}")

    _apply_host_env(host)
    _save_host_cache(host)
    return host


def _apply_host_env(host: dict):
    threads = max(1, host["cpu_cores"] - 2)
    os.environ["OLLAMA_NUM_THREADS"] = str(threads)
    if host.get("has_gpu"):
        os.environ["OLLAMA_GPU_LAYERS"] = "999"


# -- Step 4: Ollama -------------------------------------------------------------

def server_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_ollama():
    model = str(read_config("llm.model", "mistral") or "mistral")
    auto_select = bool(read_config("llm.auto_select", True))
    model_label = "auto" if auto_select else model
    start_step(f"model server ({model_label})")

    if not shutil.which("ollama"):
        local_bin = ROOT / "models" / "ollama" / "bin"
        default_install = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
        if (local_bin / "ollama.exe").exists():
            os.environ["PATH"] = str(local_bin) + os.pathsep + os.environ.get("PATH", "")
        elif (default_install / "ollama.exe").exists():
            os.environ["PATH"] = str(default_install) + os.pathsep + os.environ.get("PATH", "")

    if not shutil.which("ollama"):
        if sys.platform != "win32":
            print_sub(
                "Install Ollama from https://ollama.com/download, then re-run run.sh.",
                C.YELLOW,
            )
            end_step(f"model server ({model})", "failed", C.RED)
            sys.exit(1)
        print()
        print_sub("Ollama not found on this machine.", C.YELLOW)
        try:
            answer = input("  Install Ollama now? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in {"y", "yes"}:
            print(f"\r  {C.PURPLE}*{C.RESET}  {C.DIM}{f'model server ({model_label})':<26}{C.RESET} [{C.RED}failed{C.RESET}]", flush=True)
            sys.exit(1)
        _install_ollama()

    if not server_running():
        print(f"\r  {C.PURPLE}*{C.RESET}  {C.DIM}{f'model server ({model_label})':<26}{C.RESET} [{C.CYAN}starting...{C.RESET}]", end="", flush=True)
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for i in range(15):
            if server_running():
                break
            time.sleep(0.3)
        else:
            end_step(f"model server ({model_label})", "ready", C.YELLOW, sub_msg="Ollama slow to start, but continuing...")
            os.environ["XIA_OLLAMA_VERIFIED"] = "1"
            return

    os.environ["XIA_OLLAMA_VERIFIED"] = "1"

    has_model = _has_any_model() if auto_select else False
    if auto_select and has_model:
        end_step(
            f"model server ({model_label})",
            "ready",
            sub_msg="using the best downloaded model for this PC",
        )
        return

    has_model = _ensure_model(model)
    if has_model:
        end_step(f"model server ({model_label})", "ready")


def _install_ollama():
    if sys.platform != "win32":
        print_sub("Automatic Ollama installation is only supported on Windows.", C.RED)
        sys.exit(1)

    installer = Path(os.environ.get("TEMP", ROOT)) / "OllamaSetup.exe"
    print_sub("Downloading Ollama installer...")
    try:
        urllib.request.urlretrieve(OLLAMA_URL, installer, _progress)
        print()
    except Exception as e:
        print_sub(f"Download failed: {e}", C.RED)
        sys.exit(1)
    print_sub("Running installer silently (please wait)...")
    try:
        subprocess.run(f'start /wait "" "{installer}" /S', shell=True, check=True)
    except Exception as e:
        print_sub(f"Failed to run installer: {e}", C.RED)
        sys.exit(1)

    default_install = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
    if (default_install / "ollama.exe").exists():
        os.environ["PATH"] = str(default_install) + os.pathsep + os.environ.get("PATH", "")

    if shutil.which("ollama"):
        print_sub("Ollama installed successfully.")
    else:
        print_sub("Ollama may need a terminal restart to appear in PATH.", C.YELLOW)


def _ensure_model(model: str) -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = json.loads(r.read())
            names = [m["name"] for m in data.get("models", [])]
            model_base = model.split(":")[0]
            found = any(
                n == model or n.split(":")[0] == model_base
                for n in names
            )
            if found:
                return True
    except Exception:
        return False

    print()
    print_sub(f"Model '{model}' not downloaded yet (~4-5GB).", C.YELLOW)
    try:
        answer = input(f"  Download '{model}' now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer not in {"y", "yes"}:
        print_sub(f"Skipping model download. Run manually: ollama pull {model}", C.YELLOW)
        return True
    print_sub(f"Pulling '{model}'...")
    subprocess.run(["ollama", "pull", model])
    return True


def _has_any_model() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            return bool(json.loads(r.read()).get("models", []))
    except Exception:
        return False


def _progress(count, block, total):
    if total > 0:
        pct = min(100, count * block * 100 // total)
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"\r     {C.DIM}[{bar}] {pct}%{C.RESET}", end="", flush=True)


# -- Step 5: Health check -------------------------------------------------------

def run_health_check():
    start_step("integrity check")
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from core.health import HealthChecker
        checker = HealthChecker()
        ok_flag, issues = checker.run()
        errors   = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        if errors:
            print()
            checker.print_report(issues)
            sys.exit(1)
        if warnings:
            print()
            for w in warnings:
                print_sub(f"{w.check}: {w.message}", C.YELLOW)
        end_step("integrity check", "passed")
    except Exception as e:
        end_step("integrity check", "skipped", C.YELLOW, sub_msg=str(e))


# -- Step 6: Launch -------------------------------------------------------------

def launch():
    start_step("starting core")
    if not MAIN_PY.exists():
        end_step("starting core", "failed", C.RED, sub_msg=f"main.py not found")
        sys.exit(1)

    env = os.environ.copy()
    env["XIA_ROOT"] = str(ROOT)

    end_step("starting core", "ok")
    print(f"  {C.DIM}{'-'*48}{C.RESET}")

    result = subprocess.run(
        [str(VENV_PY), str(MAIN_PY)],
        env=env,
        cwd=str(ROOT),
    )

    print(f"  {C.DIM}{'-'*48}{C.RESET}")
    if result.returncode not in {0, 130}:  # 130 = Ctrl+C
        print(f"  {C.RED}[ERROR]  xia exited with code {result.returncode}{C.RESET}")
        sys.exit(result.returncode)


# -- Main -----------------------------------------------------------------------

def main():
    if sys.platform == "win32":
        subprocess.run("", shell=True)

    print()
    print(f"  {C.PURPLE}xia{C.RESET}  -  booting...")
    print()

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
