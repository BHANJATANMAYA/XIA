"""
test_browser.py — Verify browser and LeetCode tools.

Run AFTER install_browser.py:
    .venv\Scripts\python test_browser.py
"""

import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))


def check(label, condition, fix=""):
    status = "  OK  " if condition else " FAIL "
    symbol = "✓" if condition else "✗"
    print(f"  [{status}] {symbol} {label}")
    if not condition and fix:
        print(f"         → {fix}")
    return condition


def main():
    all_ok = True
    print()
    print("=" * 55)
    print("  xia — Browser & LeetCode Tool Verification")
    print("=" * 55)

    # ── File checks ────────────────────────────────────────────────────────
    print("\n[ New files ]")
    for f in ["tools/browser.py", "tools/leetcode.py", "install_browser.py"]:
        all_ok &= check(f, (root / f).exists())

    # ── Playwright installed ───────────────────────────────────────────────
    print("\n[ Playwright ]")
    try:
        from playwright.sync_api import sync_playwright
        all_ok &= check("playwright package installed", True)
    except ImportError:
        all_ok &= check("playwright installed", False,
                        "Run: .venv\\Scripts\\python install_browser.py")
        _summary(all_ok); return

    # ── Browser tool import ────────────────────────────────────────────────
    print("\n[ Browser tool ]")
    try:
        from tools.browser import BrowserTool
        all_ok &= check("BrowserTool imports", True)
    except ImportError as e:
        all_ok &= check("BrowserTool imports", False, str(e))
        _summary(all_ok); return

    # ── Headless browser smoke test ────────────────────────────────────────
    print("\n[ Headless browser smoke test ]")
    browser = BrowserTool(headless=True)

    print("  Starting headless browser...")
    r = browser.execute(action="navigate", url="https://example.com", timeout=15000)
    all_ok &= check("navigate to example.com", r.success, r.error or "")

    if r.success:
        r2 = browser.execute(action="get_title")
        all_ok &= check("get_title() works", r2.success)
        print(f"         Title: {r2.output}")

        r3 = browser.execute(action="extract_text")
        all_ok &= check("extract_text() works", r3.success and len(r3.output) > 10)
        print(f"         Text preview: {r3.output[:60]}...")

        r4 = browser.execute(action="get_url")
        all_ok &= check("get_url() works", r4.success)

        browser.execute(action="close")
        all_ok &= check("close() works", True)

    # ── LeetCode tool import ───────────────────────────────────────────────
    print("\n[ LeetCode tool ]")
    try:
        from tools.leetcode import LeetCodeTool
        all_ok &= check("LeetCodeTool imports", True)
    except ImportError as e:
        all_ok &= check("LeetCodeTool imports", False, str(e))

    # ── Registry includes new tools ────────────────────────────────────────
    print("\n[ Registry ]")
    try:
        from tools.registry import build_default_registry
        registry = build_default_registry(llm=None)
        names = registry.list_names()
        all_ok &= check("browser registered",  "browser"  in names)
        all_ok &= check("leetcode registered", "leetcode" in names)
        print(f"         All tools: {', '.join(names)}")
    except Exception as e:
        all_ok &= check("Registry with browser+leetcode", False, str(e))

    # ── LeetCode fetch test (no submit) ───────────────────────────────────
    print("\n[ LeetCode problem fetch (requires internet) ]")
    try:
        from tools.browser import BrowserTool
        from tools.leetcode import LeetCodeTool

        browser2 = BrowserTool(headless=True)
        lc = LeetCodeTool(browser_tool=browser2, llm=None)

        print("  Fetching 'two-sum' problem page...")
        result = lc.execute(action="fetch", problem="two-sum")

        if result.success:
            all_ok &= check("Fetched LeetCode problem page", True)
            has_content = len(result.output) > 100
            all_ok &= check("Problem content extracted", has_content,
                            "LeetCode may require login for full content")
            print(f"         Preview: {result.output[:120].strip()}...")
        else:
            all_ok &= check("Fetched LeetCode problem", False, result.error or "")
            print("         Note: LeetCode may require login for full problem access")

        browser2.execute(action="close")

    except Exception as e:
        all_ok &= check("LeetCode fetch", False, str(e))

    _summary(all_ok)


def _summary(all_ok):
    print()
    print("=" * 55)
    if all_ok:
        print("  All checks passed!")
        print()
        print("  Try in xia:")
        print("    'open google.com and search for Python news'")
        print("    'solve leetcode problem two-sum'")
        print("    'go to github.com/trending and tell me what's popular'")
    else:
        print("  Some checks failed.")
        print("  If playwright is missing: run install_browser.py first")
    print("=" * 55)
    print()
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
