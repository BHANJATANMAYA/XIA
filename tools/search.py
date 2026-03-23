"""
tools/search.py — Web Search Tool

Gives xia the ability to search the internet in real time.
Supports multiple providers so you can use whatever you have access to:

  1. DuckDuckGo  — free, no API key needed (default)
  2. SerpAPI     — reliable, needs SERPAPI_KEY in .env
  3. Tavily      — built for AI agents, needs TAVILY_API_KEY in .env

Provider priority: uses whatever is configured in config.yaml.
Falls back to DuckDuckGo if no API keys are set.

Agent calls this as:
  {
    "tool": "search",
    "input": {
      "query": "latest Python 3.13 features",
      "max_results": 5
    }
  }
"""

import json
import os
import urllib.parse
import urllib.request
from typing import List, Optional

import httpx

from core.config import cfg
from core.logger import get_logger
from tools.base import BaseTool, ToolParam, ToolResult, ToolSchema

log = get_logger(__name__)


# ── Result type ────────────────────────────────────────────────────────────────

class SearchResult:
    def __init__(self, title: str, url: str, snippet: str):
        self.title   = title
        self.url     = url
        self.snippet = snippet

    def __str__(self) -> str:
        return f"[{self.title}]\n{self.snippet}\nSource: {self.url}"


# ── Search Tool ────────────────────────────────────────────────────────────────

class SearchTool(BaseTool):

    name        = "search"
    description = (
        "Search the internet for current information. "
        "Use for news, facts, documentation, prices, weather, or anything "
        "that requires up-to-date information beyond your training data."
    )

    def __init__(self):
        self._provider = cfg.tools.search.provider
        self._max_results = cfg.tools.search.max_results
        self._client = httpx.Client(timeout=15)

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            params=[
                ToolParam("query",       "string",  "The search query",                    required=True),
                ToolParam("max_results", "integer", "Number of results to return (1–10)",  required=False, default=5),
                ToolParam("fetch_page",  "boolean", "Also fetch the top result's full page content", required=False, default=False),
            ],
        )

    def execute(
        self,
        query: str,
        max_results: int = None,
        fetch_page: bool = False,
        **_,
    ) -> ToolResult:

        query = query.strip()
        if not query:
            return self._err("Search query cannot be empty.")

        max_results = min(int(max_results or self._max_results), 10)
        log.info("search: query=%r provider=%s max=%d", query[:60], self._provider, max_results)

        # ── Run search ────────────────────────────────────────────────────
        try:
            results = self._search(query, max_results)
        except Exception as e:
            log.error("Search failed: %s", e)
            return self._err(f"Search failed: {e}")

        if not results:
            return self._ok(f"No results found for: {query}")

        # ── Format results ────────────────────────────────────────────────
        lines = [f"Search results for: '{query}'\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}")
            lines.append(f"   {r.snippet}")
            lines.append(f"   URL: {r.url}")
            lines.append("")

        output = "\n".join(lines).strip()

        # ── Optionally fetch top result ───────────────────────────────────
        if fetch_page and results:
            page_content = self._fetch_page(results[0].url)
            if page_content:
                output += f"\n\n--- Full content from top result ---\n{page_content[:3000]}"

        return self._ok(output)

    # ── Provider dispatch ──────────────────────────────────────────────────────

    def _search(self, query: str, max_results: int) -> List[SearchResult]:
        provider = self._provider.lower()

        # Check for API keys and pick best available provider
        serpapi_key = os.environ.get("SERPAPI_KEY", "")
        tavily_key  = os.environ.get("TAVILY_API_KEY", "")

        if provider == "serpapi" and serpapi_key:
            return self._search_serpapi(query, max_results, serpapi_key)
        elif provider == "tavily" and tavily_key:
            return self._search_tavily(query, max_results, tavily_key)
        else:
            if provider not in {"duckduckgo"} and not (serpapi_key or tavily_key):
                log.info("No API key found for %s — falling back to DuckDuckGo", provider)
            return self._search_duckduckgo(query, max_results)

    # ── DuckDuckGo (free, no key) ──────────────────────────────────────────────

    def _search_duckduckgo(self, query: str, max_results: int) -> List[SearchResult]:
        """
        Uses DuckDuckGo's Instant Answer API + HTML scrape fallback.
        No API key required.
        """
        results = []

        # Try DDG Instant Answer API first
        try:
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
            encoded = urllib.parse.urlencode(params)
            resp = self._client.get(f"{url}?{encoded}", headers={"User-Agent": "xia-agent/1.0"})
            data = resp.json()

            # AbstractText — the main answer
            if data.get("AbstractText"):
                results.append(SearchResult(
                    title=data.get("Heading", query),
                    url=data.get("AbstractURL", ""),
                    snippet=data["AbstractText"][:300],
                ))

            # RelatedTopics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(SearchResult(
                        title=topic.get("Text", "")[:60],
                        url=topic.get("FirstURL", ""),
                        snippet=topic.get("Text", "")[:200],
                    ))
                    if len(results) >= max_results:
                        break

        except Exception as e:
            log.warning("DDG Instant Answer failed: %s", e)

        # If we got nothing useful, try the HTML search
        if not results:
            results = self._search_duckduckgo_html(query, max_results)

        return results[:max_results]

    def _search_duckduckgo_html(self, query: str, max_results: int) -> List[SearchResult]:
        """Scrape DuckDuckGo HTML results as fallback."""
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            resp = self._client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            results = []
            text = resp.text

            # Simple extraction — look for result blocks
            import re
            # Extract titles and snippets from DDG HTML
            title_pattern = re.compile(r'class="result__a"[^>]*>(.*?)</a>', re.DOTALL)
            snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</span>', re.DOTALL)
            url_pattern = re.compile(r'class="result__url"[^>]*>(.*?)</a>', re.DOTALL)

            titles   = [re.sub(r'<[^>]+>', '', t).strip() for t in title_pattern.findall(text)]
            snippets = [re.sub(r'<[^>]+>', '', s).strip() for s in snippet_pattern.findall(text)]
            urls     = [re.sub(r'<[^>]+>', '', u).strip() for u in url_pattern.findall(text)]

            for i in range(min(max_results, len(titles))):
                results.append(SearchResult(
                    title=titles[i] if i < len(titles) else f"Result {i+1}",
                    url=urls[i] if i < len(urls) else "",
                    snippet=snippets[i] if i < len(snippets) else "",
                ))

            return results

        except Exception as e:
            log.warning("DDG HTML scrape failed: %s", e)
            return []

    # ── SerpAPI ───────────────────────────────────────────────────────────────

    def _search_serpapi(self, query: str, max_results: int, api_key: str) -> List[SearchResult]:
        try:
            params = {
                "q": query,
                "api_key": api_key,
                "num": max_results,
                "engine": "google",
            }
            resp = self._client.get("https://serpapi.com/search", params=params)
            data = resp.json()

            results = []
            for r in data.get("organic_results", [])[:max_results]:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("link", ""),
                    snippet=r.get("snippet", ""),
                ))
            return results

        except Exception as e:
            log.error("SerpAPI search failed: %s — falling back to DDG", e)
            return self._search_duckduckgo(query, max_results)

    # ── Tavily ────────────────────────────────────────────────────────────────

    def _search_tavily(self, query: str, max_results: int, api_key: str) -> List[SearchResult]:
        try:
            resp = self._client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            data = resp.json()

            results = []
            for r in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", "")[:300],
                ))
            return results

        except Exception as e:
            log.error("Tavily search failed: %s — falling back to DDG", e)
            return self._search_duckduckgo(query, max_results)

    # ── Page fetcher ──────────────────────────────────────────────────────────

    def _fetch_page(self, url: str) -> str:
        """Fetch and extract readable text from a URL."""
        if not url or not url.startswith("http"):
            return ""
        try:
            resp = self._client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, follow_redirects=True)

            import re
            text = resp.text
            # Strip scripts and styles
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            # Strip all HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Collapse whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:5000]
        except Exception as e:
            log.warning("Page fetch failed for %s: %s", url, e)
            return ""
