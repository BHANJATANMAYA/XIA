"""
tools/browser.py — Browser Automation Tool

Gives xia the ability to control a real Chrome browser.
Built on Playwright — reliable, fast, and works headlessly or visibly.

Supported actions:
  navigate      — Go to a URL
  click         — Click an element by CSS selector or text
  type          — Type text into the focused or selected element
  clear         — Clear an input field
  extract_text  — Get all readable text from the page or an element
  extract_html  — Get raw HTML of page or element
  screenshot    — Take a screenshot (saved to workspace)
  scroll        — Scroll up/down
  wait          — Wait for an element or N seconds
  evaluate      — Run JavaScript on the page
  get_url       — Get current page URL
  get_title     — Get current page title
  select        — Select an option from a dropdown
  press         — Press a keyboard key (Enter, Tab, Escape etc.)
  hover         — Hover over an element
  close         — Close the browser

Agent calls this as:
  {
    "tool": "browser",
    "input": {
      "action": "navigate",
      "url": "https://leetcode.com/problems/two-sum"
    }
  }
"""

import base64
import time
from pathlib import Path
from typing import Optional

from core.config import cfg
from core.logger import get_logger
from core.paths import PATHS
from tools.base import BaseTool, ToolParam, ToolResult, ToolSchema

log = get_logger(__name__)


class BrowserTool(BaseTool):

    name        = "browser"
    description = (
        "Control a real Chrome browser — navigate websites, click buttons, "
        "type text, extract content, take screenshots, and automate any web task."
    )

    def __init__(self, headless: bool = False):
        self._headless   = headless
        self._playwright = None
        self._browser    = None
        self._page       = None
        self._started    = False

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            params=[
                ToolParam("action",   "string", "One of: navigate, click, type, clear, extract_text, extract_html, screenshot, scroll, wait, evaluate, get_url, get_title, select, press, hover, close", required=True),
                ToolParam("url",      "string", "URL to navigate to (for navigate action)", required=False),
                ToolParam("selector", "string", "CSS selector or text to target an element", required=False),
                ToolParam("text",     "string", "Text to type or search for", required=False),
                ToolParam("value",    "string", "Value for select dropdowns or evaluate JS", required=False),
                ToolParam("timeout",  "integer","Wait timeout in milliseconds (default 10000)", required=False, default=10000),
                ToolParam("save_as",  "string", "Filename for screenshot (default: screenshot.png)", required=False),
            ],
        )

    def execute(
        self,
        action: str,
        url: str = "",
        selector: str = "",
        text: str = "",
        value: str = "",
        timeout: int = 10000,
        save_as: str = "screenshot.png",
        **_,
    ) -> ToolResult:

        action = action.lower().strip()

        # Close doesn't need browser running
        if action == "close":
            return self._close()

        # Start browser if not running
        if not self._started:
            result = self._start_browser()
            if not result.success:
                return result

        log.debug("browser: action=%s selector=%r text=%r", action, selector[:40] if selector else "", text[:40] if text else "")

        dispatch = {
            "navigate":     lambda: self._navigate(url, timeout),
            "click":        lambda: self._click(selector, text, timeout),
            "type":         lambda: self._type(selector, text),
            "clear":        lambda: self._clear(selector),
            "extract_text": lambda: self._extract_text(selector),
            "extract_html": lambda: self._extract_html(selector),
            "screenshot":   lambda: self._screenshot(save_as),
            "scroll":       lambda: self._scroll(value),
            "wait":         lambda: self._wait(selector, value, timeout),
            "evaluate":     lambda: self._evaluate(value or text),
            "get_url":      lambda: self._get_url(),
            "get_title":    lambda: self._get_title(),
            "select":       lambda: self._select(selector, value or text),
            "press":        lambda: self._press(value or text),
            "hover":        lambda: self._hover(selector, timeout),
        }

        handler = dispatch.get(action)
        if handler is None:
            return self._err(f"Unknown action '{action}'. Valid: {', '.join(dispatch)}")

        try:
            return handler()
        except Exception as e:
            log.error("Browser action '%s' failed: %s", action, e)
            return self._err(f"Browser error during '{action}': {e}")

    # ── Browser lifecycle ──────────────────────────────────────────────────

    def _start_browser(self) -> ToolResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return self._err(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        try:
            log.info("Starting browser (headless=%s)", self._headless)
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self._headless,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            self._page = self._browser.new_page(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._started = True
            log.info("Browser started")
            return self._ok("Browser started")
        except Exception as e:
            return self._err(f"Failed to start browser: {e}\nRun: playwright install chromium")

    def _close(self) -> ToolResult:
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
            self._started    = False
            self._page       = None
            self._browser    = None
            self._playwright = None
            return self._ok("Browser closed")
        except Exception as e:
            return self._err(f"Error closing browser: {e}")

    # ── Actions ────────────────────────────────────────────────────────────

    def _navigate(self, url: str, timeout: int) -> ToolResult:
        if not url:
            return self._err("URL required for navigate action")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        self._page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        time.sleep(1)  # Let JS settle
        title = self._page.title()
        current = self._page.url
        return self._ok(f"Navigated to: {current}\nPage title: {title}")

    def _click(self, selector: str, text: str, timeout: int) -> ToolResult:
        if selector:
            self._page.click(selector, timeout=timeout)
            return self._ok(f"Clicked: {selector}")
        elif text:
            # Try to find by text
            self._page.get_by_text(text, exact=False).first.click(timeout=timeout)
            return self._ok(f"Clicked element with text: {text}")
        return self._err("Provide 'selector' or 'text' for click action")

    def _type(self, selector: str, text: str) -> ToolResult:
        if not text:
            return self._err("'text' required for type action")
        if selector:
            self._page.click(selector)
            self._page.type(selector, text, delay=50)
        else:
            self._page.keyboard.type(text, delay=50)
        return self._ok(f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}")

    def _clear(self, selector: str) -> ToolResult:
        if not selector:
            return self._err("'selector' required for clear action")
        self._page.fill(selector, "")
        return self._ok(f"Cleared: {selector}")

    def _extract_text(self, selector: str) -> ToolResult:
        if selector:
            try:
                el = self._page.query_selector(selector)
                if not el:
                    return self._err(f"Element not found: {selector}")
                text = el.inner_text()
            except Exception as e:
                return self._err(f"Could not extract text from {selector}: {e}")
        else:
            text = self._page.inner_text("body")

        # Clean up
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        clean = "\n".join(lines)

        if len(clean) > 8000:
            clean = clean[:8000] + f"\n... (truncated, {len(clean)} chars total)"

        return self._ok(clean)

    def _extract_html(self, selector: str) -> ToolResult:
        if selector:
            el = self._page.query_selector(selector)
            if not el:
                return self._err(f"Element not found: {selector}")
            html = el.inner_html()
        else:
            html = self._page.content()

        if len(html) > 5000:
            html = html[:5000] + "... (truncated)"
        return self._ok(html)

    def _screenshot(self, save_as: str) -> ToolResult:
        if not save_as.endswith(".png"):
            save_as += ".png"
        path = PATHS.workspace_dir / "screenshots" / save_as
        path.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(path), full_page=False)
        return self._ok(f"Screenshot saved: {path}")

    def _scroll(self, direction: str) -> ToolResult:
        direction = (direction or "down").lower()
        amount = -600 if direction == "up" else 600
        self._page.mouse.wheel(0, amount)
        time.sleep(0.5)
        return self._ok(f"Scrolled {direction}")

    def _wait(self, selector: str, value: str, timeout: int) -> ToolResult:
        if selector:
            self._page.wait_for_selector(selector, timeout=timeout)
            return self._ok(f"Element appeared: {selector}")
        else:
            seconds = float(value or "2")
            time.sleep(seconds)
            return self._ok(f"Waited {seconds}s")

    def _evaluate(self, js: str) -> ToolResult:
        if not js:
            return self._err("'value' required for evaluate action (JavaScript code)")
        result = self._page.evaluate(js)
        return self._ok(str(result) if result is not None else "(no return value)")

    def _get_url(self) -> ToolResult:
        return self._ok(self._page.url)

    def _get_title(self) -> ToolResult:
        return self._ok(self._page.title())

    def _select(self, selector: str, value: str) -> ToolResult:
        if not selector or not value:
            return self._err("Both 'selector' and 'value' required for select action")
        self._page.select_option(selector, value)
        return self._ok(f"Selected '{value}' in {selector}")

    def _press(self, key: str) -> ToolResult:
        if not key:
            return self._err("'value' required for press action (e.g. Enter, Tab, Escape)")
        self._page.keyboard.press(key)
        return self._ok(f"Pressed: {key}")

    def _hover(self, selector: str, timeout: int) -> ToolResult:
        if not selector:
            return self._err("'selector' required for hover action")
        self._page.hover(selector, timeout=timeout)
        return self._ok(f"Hovered: {selector}")

    def __del__(self):
        """Clean up browser on garbage collection."""
        try:
            if self._started:
                self._close()
        except Exception:
            pass
