"""
install_browser.py — Install Playwright and Chromium

Run this ONCE before using browser-based features:
    .venv\\Scripts\\python scripts/install_browser.py

This installs:
  1. playwright Python package (into venv)
  2. Chromium browser (~170MB, stored in your system, not the SSD)
"""

import subprocess
import sys
from pathlib import Path

root   = Path(__file__).resolve().parent.parent
venv_py  = root / ".venv" / "Scripts" / "python.exe"

def run(cmd):
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True)
    return result.returncode == 0


def main():
    import os
    # Direct Playwright to download and run browsers from the SSD
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(root / "models" / "playwright")

    print()
    print("=" * 50)
    print("  xia — Browser Tool Installer")
    print("=" * 50)
    print()

    py = str(venv_py) if venv_py.exists() else sys.executable

    # Step 1: Install playwright package
    print("[ Step 1 ] Installing playwright package...")
    ok = run([py, "-m", "pip", "install", "playwright", "--quiet"])
    if not ok:
        print("  FAILED. Try: pip install playwright")
        sys.exit(1)
    print("  OK\n")

    # Step 2: Install Chromium browser
    print("[ Step 2 ] Installing Chromium (~170MB)...")
    print("  This is a one-time download.")
    ok = run([py, "-m", "playwright", "install", "chromium"])
    if not ok:
        print("  FAILED. Try: playwright install chromium")
        sys.exit(1)
    print("  OK\n")

    # Step 3: Quick smoke test
    print("[ Step 3 ] Smoke test...")
    test = subprocess.run(
        [py, "-c",
         "from playwright.sync_api import sync_playwright; "
         "p = sync_playwright().start(); "
         "b = p.chromium.launch(headless=True); "
         "pg = b.new_page(); pg.goto('https://example.com'); "
         "print('title:', pg.title()); b.close(); p.stop()"],
        capture_output=True, text=True
    )
    if test.returncode == 0:
        print(f"  {test.stdout.strip()}")
        print("  OK\n")
    else:
        print(f"  Warning: smoke test failed: {test.stderr[:200]}")
        print("  Browser may still work — try running xia.\n")

    print("=" * 50)
    print("  Browser tool ready!")
    print("  Launch xia and try:")
    print("    'open google.com and search for Python tutorials'")
    print("    'open example.com and summarize the page'")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()

