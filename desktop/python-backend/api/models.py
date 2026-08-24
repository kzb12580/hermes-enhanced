"""Proxy endpoint for fetching available models from external providers.

The frontend cannot call external APIs directly due to CORS restrictions,
so we proxy the request through the backend.
"""

import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("hermes-backend.models")
router = APIRouter()


class ModelsResponse(BaseModel):
    success: bool
    models: list[str] = []
    error: Optional[str] = None
    latency_ms: Optional[int] = None


class ModelsRequest(BaseModel):
    base_url: str
    api_key: str = ""
    proxy_url: str = ""


async def _fetch_models(base_url: str, api_key: str = "", proxy_url: str = "") -> ModelsResponse:
    """Fetch available models from an OpenAI / Anthropic / Ollama compatible endpoint."""
    url = base_url.strip().rstrip("/")
    if not url:
        return ModelsResponse(success=False, models=[], error="API 地址不能为空")

    # Normalize URL for /v1/models
    base_endpoint = url
    if base_endpoint.endswith("/v1"):
        models_url = f"{base_endpoint}/models"
    else:
        models_url = f"{base_endpoint}/v1/models"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Anthropic specific headers
    if "anthropic.com" in url:
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"

    client_kwargs: dict = {"timeout": 15.0, "verify": True}
    if proxy_url:
        client_kwargs["proxy"] = proxy_url
    else:
        client_kwargs["trust_env"] = True

    start_time = time.perf_counter()

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(models_url, headers=headers)

            # Fallback for Ollama or custom gateways if /v1/models returns 404
            if resp.status_code == 404:
                # Try direct URL /models or Ollama /api/tags
                alt_urls = [
                    f"{url}/models",
                    f"{url}/api/tags",
                ]
                for alt_url in alt_urls:
                    try:
                        alt_resp = await client.get(alt_url, headers=headers)
                        if alt_resp.status_code == 200:
                            resp = alt_resp
                            break
                    except Exception:
                        continue

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        if resp.status_code != 200:
            error_text = resp.text[:200]
            logger.warning("Models fetch failed: HTTP %d — %s", resp.status_code, error_text)
            return ModelsResponse(
                success=False,
                models=[],
                error=f"HTTP {resp.status_code}: {error_text or resp.reason_phrase}",
                latency_ms=latency_ms,
            )

        data = resp.json()

        # 1. OpenAI / Anthropic format: { data: [{ id: "model-name", ... }] }
        if isinstance(data.get("data"), list):
            models = [
                m.get("id") or m.get("name", "")
                for m in data["data"]
                if isinstance(m, dict) and (m.get("id") or m.get("name"))
            ]
            # Deduplicate while preserving order
            seen = set()
            unique_models = [m for m in models if m and not (m in seen or seen.add(m))]
            logger.info("Found %d models via data array (latency: %dms)", len(unique_models), latency_ms)
            return ModelsResponse(success=True, models=unique_models, latency_ms=latency_ms)

        # 2. Ollama format: { models: [{ name: "llama3:latest", ... }] }
        if isinstance(data.get("models"), list):
            models = [
                m.get("name") or m.get("model", "")
                for m in data["models"]
                if isinstance(m, dict) and (m.get("name") or m.get("model"))
            ]
            seen = set()
            unique_models = [m for m in models if m and not (m in seen or seen.add(m))]
            logger.info("Found %d models via Ollama models array (latency: %dms)", len(unique_models), latency_ms)
            return ModelsResponse(success=True, models=unique_models, latency_ms=latency_ms)

        # 3. Flat list: ["model1", "model2"] or [{ id: "model1" }]
        if isinstance(data, list):
            models = [m if isinstance(m, str) else (m.get("id") or m.get("name", "")) for m in data if isinstance(m, (str, dict))]
            seen = set()
            unique_models = [m for m in models if m and not (m in seen or seen.add(m))]
            logger.info("Found %d models via flat list (latency: %dms)", len(unique_models), latency_ms)
            return ModelsResponse(success=True, models=unique_models, latency_ms=latency_ms)

        logger.warning("Unexpected response format: %s", str(data)[:200])
        return ModelsResponse(
            success=False,
            models=[],
            error="返回数据格式不符合预期",
            latency_ms=latency_ms,
        )

    except httpx.ConnectError as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error("Connection failed to %s: %s", url, e)
        return ModelsResponse(success=False, models=[], error=f"连接失败: 无法访问 {url}", latency_ms=latency_ms)
    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error("Request timeout to %s", url)
        return ModelsResponse(success=False, models=[], error="请求超时 (15秒)", latency_ms=latency_ms)
    except Exception as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error("Unexpected error fetching models from %s: %s", url, e)
        return ModelsResponse(success=False, models=[], error=f"未知错误: {e}", latency_ms=latency_ms)


@router.post("/api/models", response_model=ModelsResponse)
async def list_models_post(request: ModelsRequest):
    """Fetch models without exposing api_key in URL/query logs."""
    return await _fetch_models(request.base_url, request.api_key, request.proxy_url)
