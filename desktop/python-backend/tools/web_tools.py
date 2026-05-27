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
        # Validate the DuckDuckGo URL (hardcoded, but validate for good measure)
        ddg_url = "https://html.duckduckgo.com/html/"
        err = _validate_url(ddg_url)
        if err:
            return err

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    ddg_url,
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )

            if resp.status_code != 200:
                return f"Error: Search returned HTTP {resp.status_code}"

            html = resp.text

            # Parse results from DuckDuckGo HTML
            results = []
            result_blocks = re.findall(
                r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>.*?'
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                html, re.DOTALL,
            )

            for result_url, title, snippet in result_blocks[:limit]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                url_match = re.search(r'uddg=([^&]+)', result_url)
                if url_match:
                    result_url = unquote(url_match.group(1))
                if title and result_url:
                    results.append(f"**{title}**\n{result_url}\n{snippet}\n")

            if not results:
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
