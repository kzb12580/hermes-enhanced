"""Web tools — search and extract web content."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import unquote, urlparse

import httpx

from .base import BaseTool
from . import register

MAX_SEARCH_RESULTS = 5
MAX_EXTRACT_LENGTH = 20_000


def _validate_url(url: str) -> str | None:
    """Validate URL against SSRF attacks.

    Returns ``None`` if the URL is safe, or an error message string if not.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "Error: Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return "Error: Only http/https URLs are allowed"

    hostname = parsed.hostname
    if not hostname:
        return "Error: URL has no hostname"

    # Resolve hostname to check IP ranges
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        # Cannot resolve — let httpx handle it (could be a transient DNS error)
        return None

    _PRIVATE_NETS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _PRIVATE_NETS:
            if ip in net:
                return f"Error: URL resolves to private/reserved IP {ip} — SSRF blocked"

    return None


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web using DuckDuckGo. Returns titles, URLs, and snippets."
    requires_network = True
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, limit: int = MAX_SEARCH_RESULTS, **kwargs) -> str:
        """Search using DuckDuckGo Lite (more reliable than HTML endpoint)."""
        results = []

        # Strategy 1: DuckDuckGo Lite (lightweight, stable)
        try:
            results = await self._search_ddg_lite(query, limit)
            if results:
                return f"Search results for: {query}\n\n" + "\n".join(results)
        except Exception as e:
            pass  # Fall through to next strategy

        # Strategy 2: DuckDuckGo HTML (fallback)
        try:
            results = await self._search_ddg_html(query, limit)
            if results:
                return f"Search results for: {query}\n\n" + "\n".join(results)
        except Exception as e:
            pass

        # Strategy 3: Basic web scraping (last resort)
        try:
            results = await self._search_basic(query, limit)
            if results:
                return f"Search results for: {query}\n\n" + "\n".join(results)
        except Exception as e:
            pass

        if not results:
            return f"No search results found for: {query}. DuckDuckGo may be temporarily unavailable."
        return f"Search results for: {query}\n\n" + "\n".join(results)

    async def _search_ddg_lite(self, query: str, limit: int) -> list[str]:
        """Search using DuckDuckGo Lite endpoint."""
        url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.post(
                url,
                data={"q": query, "b": ""},
                headers=headers,
            )

        if resp.status_code != 200:
            return []

        html = resp.text
        results = []

        # Parse DuckDuckGo Lite HTML (simpler structure)
        # Result links are in <a> tags with class="result-link"
        link_pattern = re.compile(r'<a[^>]+class="result-link"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
        snippet_pattern = re.compile(r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>', re.DOTALL)

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title) in enumerate(links[:limit]):
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            # Extract real URL from DuckDuckGo redirect
            if "uddg=" in url:
                url_match = re.search(r'uddg=([^&]+)', url)
                if url_match:
                    url = unquote(url_match.group(1))

            if title and url:
                result_text = f"**{title}**\n{url}"
                if snippet:
                    result_text += f"\n{snippet}"
                results.append(result_text)

        return results

    async def _search_ddg_html(self, query: str, limit: int) -> list[str]:
        """Search using DuckDuckGo HTML endpoint (fallback)."""
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.post(
                url,
                data={"q": query, "b": ""},
                headers=headers,
            )

        if resp.status_code != 200:
            return []

        html = resp.text
        results = []

        # Try multiple parsing patterns (DuckDuckGo changes frequently)
        patterns = [
            # Pattern 1: Classic result__a
            (
                r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>.*?'
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                re.DOTALL
            ),
            # Pattern 2: Newer structure
            (
                r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                0
            ),
            # Pattern 3: Generic links
            (
                r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>',
                re.DOTALL
            ),
        ]

        for pattern, flags in patterns:
            matches = re.findall(pattern, html, flags)
            if matches:
                for match in matches[:limit]:
                    if len(match) == 3:
                        result_url, title, snippet = match
                    else:
                        result_url, title = match
                        snippet = ""

                    title = re.sub(r'<[^>]+>', '', title).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippet).strip()

                    # Extract real URL
                    if "uddg=" in result_url:
                        url_match = re.search(r'uddg=([^&]+)', result_url)
                        if url_match:
                            result_url = unquote(url_match.group(1))

                    if title and result_url:
                        result_text = f"**{title}**\n{result_url}"
                        if snippet:
                            result_text += f"\n{snippet}"
                        results.append(result_text)

                if results:
                    break

        return results

    async def _search_basic(self, query: str, limit: int) -> list[str]:
        """Basic search using DuckDuckGo API (last resort)."""
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=headers)

        if resp.status_code != 200:
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        results = []

        # Extract results from different fields
        if data.get("Abstract"):
            results.append(f"**{data.get('Heading', 'Result')}**\n{data.get('AbstractURL', '')}\n{data['Abstract']}")

        if data.get("RelatedTopics"):
            for topic in data["RelatedTopics"][:limit]:
                if isinstance(topic, dict) and topic.get("Text"):
                    title = topic.get("Text", "").split(". ")[0] if ". " in topic.get("Text", "") else topic.get("Text", "")
                    url = topic.get("FirstURL", "")
                    if title and url:
                        results.append(f"**{title}**\n{url}")

        return results[:limit]


class WebExtractTool(BaseTool):
    name = "web_extract"
    description = "Extract text content from a web page URL."
    requires_network = True
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to extract content from"},
        },
        "required": ["url"],
    }

    async def execute(self, url: str, **kwargs) -> str:
        # SSRF protection
        err = _validate_url(url)
        if err:
            return err

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
            # Remove comments
            html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
            # Convert common elements to text
            html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
            html = re.sub(r'<p[^>]*>', '\n\n', html, flags=re.IGNORECASE)
            html = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n\n**\1**\n', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<li[^>]*>', '\n- ', html, flags=re.IGNORECASE)
            # Remove remaining tags
            text = re.sub(r'<[^>]+>', '', html)
            # Decode HTML entities
            text = re.sub(r'&amp;', '&', text)
            text = re.sub(r'&lt;', '<', text)
            text = re.sub(r'&gt;', '>', text)
            text = re.sub(r'&quot;', '"', text)
            text = re.sub(r'&#?\w+;', ' ', text)
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
