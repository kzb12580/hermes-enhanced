"""Web tools — search and extract web content."""

from __future__ import annotations

import re

import httpx

from .base import BaseTool
from . import register

MAX_SEARCH_RESULTS = 5
MAX_EXTRACT_LENGTH = 20_000


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web using DuckDuckGo. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, limit: int = MAX_SEARCH_RESULTS, **kwargs) -> str:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                # Use DuckDuckGo HTML version
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )

            if resp.status_code != 200:
                return f"Error: Search returned HTTP {resp.status_code}"

            html = resp.text

            # Parse results from DuckDuckGo HTML
            results = []
            # Extract result blocks
            result_blocks = re.findall(
                r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>.*?'
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )

            for url, title, snippet in result_blocks[:limit]:
                # Clean HTML tags
                title = re.sub(r'<[^>]+>', '', title).strip()
                snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                # Decode DuckDuckGo redirect URL
                url_match = re.search(r'uddg=([^&]+)', url)
                if url_match:
                    from urllib.parse import unquote
                    url = unquote(url_match.group(1))
                if title and url:
                    results.append(f"**{title}**\n{url}\n{snippet}\n")

            if not results:
                # Fallback: try simpler parsing
                links = re.findall(r'href="(https?://[^"]+)"', html)
                titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
                for i, (link, title) in enumerate(zip(links[:limit], titles[:limit])):
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    results.append(f"**{title}**\n{link}\n")

            if not results:
                return "No search results found."

            return f"Search results for: {query}\n\n" + "\n".join(results)

        except httpx.ConnectError:
            return "Error: Cannot connect to search engine. Check your internet connection."
        except Exception as e:
            return f"Error: {e}"


class WebExtractTool(BaseTool):
    name = "web_extract"
    description = "Extract text content from a web page URL."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to extract content from"},
        },
        "required": ["url"],
    }

    async def execute(self, url: str, **kwargs) -> str:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )

            if resp.status_code != 200:
                return f"Error: HTTP {resp.status_code}"

            html = resp.text

            # Remove scripts and styles
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            # Convert common elements to text
            html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
            html = re.sub(r'<p[^>]*>', '\n\n', html, flags=re.IGNORECASE)
            html = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n\n**\1**\n', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<li[^>]*>', '\n- ', html, flags=re.IGNORECASE)
            # Remove remaining tags
            text = re.sub(r'<[^>]+>', '', html)
            # Clean whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r'[ \t]+', ' ', text)
            text = text.strip()

            if len(text) > MAX_EXTRACT_LENGTH:
                text = text[:MAX_EXTRACT_LENGTH] + f"\n... (truncated, {len(text)} chars total)"

            if not text:
                return "Error: Could not extract meaningful text from the page."

            return f"Content from {url}:\n\n{text}"

        except httpx.ConnectError:
            return f"Error: Cannot connect to {url}"
        except Exception as e:
            return f"Error: {e}"
