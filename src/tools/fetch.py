"""
tools/fetch.py — Web Page Fetcher Tool

Fetches and extracts readable text content from any URL.
Used when the agent needs to read the full content of a specific page,
not just search snippets.

Agent calls this as:
  {
    "tool": "fetch",
    "input": {
      "url": "https://docs.python.org/3/library/pathlib.html",
      "max_chars": 3000
    }
  }
"""

import re
import urllib.parse

import httpx

from core.logger import get_logger
from tools.base import BaseTool, ToolParam, ToolResult, ToolSchema

log = get_logger(__name__)

# Domains that are unlikely to be useful to fetch
BLOCKED_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "tiktok.com", "linkedin.com",
}


class FetchTool(BaseTool):

    name        = "fetch"
    description = (
        "Fetch and read the full text content of any webpage. "
        "Use after a search when you need the complete content of a specific URL, "
        "or when the user gives you a URL to read."
    )

    def __init__(self):
        self._client = httpx.Client(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            params=[
                ToolParam("url",       "string",  "The full URL to fetch (must start with https://)", required=True),
                ToolParam("max_chars", "integer", "Maximum characters to return (default 4000)",       required=False, default=4000),
            ],
        )

    def execute(self, url: str, max_chars: int = 4000, **_) -> ToolResult:
        url = url.strip()

        if not url:
            return self._err("URL cannot be empty.")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Block social media and login-walled sites
        domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
        if domain in BLOCKED_DOMAINS:
            return self._err(f"Domain '{domain}' is not supported for fetching.")

        log.info("fetch: url=%s max_chars=%d", url[:80], max_chars)

        try:
            resp = self._client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text" not in content_type and "json" not in content_type:
                return self._err(f"URL returned non-text content ({content_type}). Cannot extract text.")

            text = self._extract_text(resp.text)
            max_chars = min(int(max_chars), 8000)

            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... (truncated — {len(text)} chars total)"

            return self._ok(
                f"Content from: {url}\n"
                f"Length: {len(text)} chars\n\n"
                f"{text}"
            )

        except httpx.HTTPStatusError as e:
            return self._err(f"HTTP {e.response.status_code} fetching {url}")
        except httpx.ConnectError:
            return self._err(f"Could not connect to {url}. Check internet connection.")
        except httpx.TimeoutException:
            return self._err(f"Timed out fetching {url}.")
        except Exception as e:
            return self._err(f"Failed to fetch {url}: {e}")

    def _extract_text(self, html: str) -> str:
        """Extract clean readable text from HTML."""
        # Remove scripts, styles, and non-content tags
        html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL)
        html = re.sub(r'<nav[^>]*>.*?</nav>', ' ', html, flags=re.DOTALL)
        html = re.sub(r'<footer[^>]*>.*?</footer>', ' ', html, flags=re.DOTALL)
        html = re.sub(r'<header[^>]*>.*?</header>', ' ', html, flags=re.DOTALL)

        # Convert common block elements to newlines
        html = re.sub(r'<br\s*/?>', '\n', html)
        html = re.sub(r'<p[^>]*>', '\n', html)
        html = re.sub(r'</p>', '\n', html)
        html = re.sub(r'<h[1-6][^>]*>', '\n## ', html)
        html = re.sub(r'</h[1-6]>', '\n', html)
        html = re.sub(r'<li[^>]*>', '\n- ', html)

        # Strip remaining tags
        html = re.sub(r'<[^>]+>', ' ', html)

        # Decode HTML entities
        html = html.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        html = html.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')

        # Collapse whitespace
        html = re.sub(r' +', ' ', html)
        html = re.sub(r'\n{3,}', '\n\n', html)

        return html.strip()
