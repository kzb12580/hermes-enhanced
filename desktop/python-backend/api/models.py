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


@router.get("/api/models", response_model=ModelsResponse)
async def list_models(
    base_url: str = Query(..., description="Provider base URL (e.g. https://api.openai.com/v1)"),
    api_key: str = Query("", description="API key for authentication"),
):
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
        async with httpx.AsyncClient(timeout=15.0, verify=True) as client:
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
