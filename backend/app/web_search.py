"""Open-source web search (DuckDuckGo via `ddgs`, or a self-hosted SearXNG instance)."""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.loaders import USER_AGENT, html_to_text

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass
class WebPage:
    title: str
    url: str
    snippet: str
    content: str
    fetched: bool


class WebSearcher:
    def __init__(self, searxng_url: str | None = None, timeout: float = 12.0):
        self.searxng_url = searxng_url
        self.timeout = timeout

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        if self.searxng_url:
            return await self._search_searxng(query, max_results)
        return await asyncio.to_thread(self._search_ddgs, query, max_results)

    def _search_ddgs(self, query: str, max_results: int, attempts: int = 3) -> list[SearchResult]:
        from ddgs import DDGS

        raw: list[dict] = []
        for attempt in range(attempts):
            try:
                raw = DDGS().text(query, max_results=max_results) or []
            except Exception as exc:  # noqa: BLE001 - search backends raise many error types
                logger.warning("Web search attempt %d failed: %s", attempt + 1, exc)
            if raw:
                break
            time.sleep(1.0 + attempt)
        results = [
            SearchResult(title=r.get("title", ""), url=r.get("href", ""), snippet=r.get("body", ""))
            for r in raw
            if r.get("href")
        ]
        return results[:max_results]

    async def _search_searxng(self, query: str, max_results: int) -> list[SearchResult]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.searxng_url.rstrip('/')}/search", params={"q": query, "format": "json"}
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchResult(title=r.get("title", ""), url=r["url"], snippet=r.get("content", ""))
            for r in data.get("results", [])
            if r.get("url")
        ][:max_results]

    async def fetch_pages(
        self, results: list[SearchResult], max_chars: int = 20000
    ) -> list[WebPage]:
        """Fetch and extract the readable content of every search result concurrently."""
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=self.timeout, headers={"User-Agent": USER_AGENT}
        ) as client:

            async def fetch(result: SearchResult) -> WebPage:
                try:
                    resp = await client.get(result.url)
                    resp.raise_for_status()
                    if "html" not in resp.headers.get("content-type", "html"):
                        raise ValueError("non-HTML content")
                    title, text = await asyncio.to_thread(html_to_text, resp.text, result.url)
                    return WebPage(
                        title=result.title or title,
                        url=result.url,
                        snippet=result.snippet,
                        content=text[:max_chars],
                        fetched=bool(text),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.info("Failed to fetch %s: %s", result.url, exc)
                    return WebPage(result.title, result.url, result.snippet, result.snippet, False)

            return list(await asyncio.gather(*(fetch(r) for r in results)))
