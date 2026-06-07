"""Proxy endpoint for fetching available models from external providers.

The frontend cannot call external APIs directly due to CORS restrictions,
so we proxy the request through the backend.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger("hermes-backend.models")
router = APIRouter()


class ModelsResponse(BaseModel):
    success: bool
    models: list[str] = []
    error: Optional[str] = None


class ModelsRequest(BaseModel):
    base_url: str
    api_key: str = ""
    proxy_url: str = ""


async def _fetch_models(base_url: str, api_key: str = "", proxy_url: str = "") -> ModelsResponse:
    """Fetch available models from an OpenAI-compatible /v1/models endpoint."""
    # Normalize URL
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    models_url = f"{url}/v1/models"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info("Fetching models from %s", models_url)

    try:
        # SSRF 防护: 禁止访问内网地址
        import ipaddress
        import socket
        import urllib.parse
        try:
            parsed = urllib.parse.urlparse(models_url)
            hostname = parsed.hostname or ""
            _BLOCKED_ERROR = "不允许访问内网地址"

            # --- Phase 1: 阻止已知内网/特殊主机名 ---
            _blocked_hosts = {"localhost", "[::1]", "0.0.0.0", "::"}
            if hostname in _blocked_hosts:
                return ModelsResponse(success=False, models=[], error=_BLOCKED_ERROR)

            # --- Phase 2: 如果 host 是 IP 字面量，直接检查 ---
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return ModelsResponse(success=False, models=[], error=_BLOCKED_ERROR)
            except ValueError:
                pass  # 非 IP 字面量，继续域名解析检查

            # --- Phase 3: DNS 解析检查（防止 DNS Rebinding） ---
            try:
                resolved = socket.getaddrinfo(hostname, parsed.port or 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for _family, _type, _proto, _canonname, sockaddr in resolved:
                    resolved_ip = ipaddress.ip_address(sockaddr[0])
                    if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                        return ModelsResponse(success=False, models=[], error=_BLOCKED_ERROR)
            except (socket.gaierror, OSError):
                # DNS 解析失败 — 阻断连接，防止 DNS Rebinding 绕过
                return ModelsResponse(success=False, models=[], error="DNS 解析失败，请检查 URL 是否正确")
        except Exception as e:
            logger.warning("SSRF check error for %s: %s", base_url, e)
            # Block request if SSRF check itself fails — fail-closed
            return ModelsResponse(success=False, models=[], error=f"安全检查失败: {e}")

        # Proxy resolution: explicit proxy_url > system env vars (HTTP_PROXY/HTTPS_PROXY)
        client_kwargs: dict = {"timeout": 15.0, "verify": True}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        else:
            client_kwargs["trust_env"] = True

        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(models_url, headers=headers)

        if resp.status_code != 200:
            error_text = resp.text[:200]
            logger.warning("Models fetch failed: HTTP %d — %s", resp.status_code, error_text)
            return ModelsResponse(
                success=False,
                models=[],
                error=f"HTTP {resp.status_code}: {error_text or resp.reason_phrase}",
            )

        data = resp.json()

        # OpenAI format: { data: [{ id: "model-name", ... }] }
        if isinstance(data.get("data"), list):
            models = [
                m.get("id") or m.get("name", "")
                for m in data["data"]
                if isinstance(m, dict) and (m.get("id") or m.get("name"))
            ]
            logger.info("Found %d models", len(models))
            return ModelsResponse(success=True, models=models)

        # Some providers return a flat list
        if isinstance(data, list):
            models = [m if isinstance(m, str) else m.get("id", "") for m in data]
            models = [m for m in models if m]
            logger.info("Found %d models (flat list)", len(models))
            return ModelsResponse(success=True, models=models)

        logger.warning("Unexpected response format: %s", str(data)[:200])
        return ModelsResponse(
            success=False,
            models=[],
            error=f"Unexpected response format",
        )

    except httpx.ConnectError as e:
        logger.error("Connection failed: %s", e)
        return ModelsResponse(success=False, models=[], error=f"连接失败: {e}")
    except httpx.TimeoutException:
        logger.error("Request timeout")
        return ModelsResponse(success=False, models=[], error="请求超时 (15秒)")
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return ModelsResponse(success=False, models=[], error=f"未知错误: {e}")


@router.post("/api/models", response_model=ModelsResponse)
async def list_models_post(request: ModelsRequest):
    """Fetch models without exposing api_key in URL/query logs."""
    return await _fetch_models(request.base_url, request.api_key, request.proxy_url)


@router.get("/api/models", response_model=ModelsResponse)
async def list_models(
    base_url: str = Query(..., description="Provider base URL (e.g. https://api.openai.com/v1)"),
    api_key: str = Query("", description="API key for authentication"),
    proxy_url: str = Query("", description="Optional proxy URL (e.g. http://127.0.0.1:7890)"),
):
    """Fetch available models from an OpenAI-compatible /v1/models endpoint."""
    return await _fetch_models(base_url, api_key, proxy_url)
