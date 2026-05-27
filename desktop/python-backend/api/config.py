"""Config API — read and update application settings."""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

# Default configuration
_config: dict = {
    "model": "hermes-3-llama-3.1-8b",
    "temperature": 0.7,
    "max_tokens": 4096,
    "theme": "dark",
    "language": "en",
    "auto_save": True,
    "streaming": True,
    "backend_port": 9876,
}


class ConfigUpdate(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = Field(
        default=None, ge=0.0, le=2.0,
        description="Sampling temperature, 0.0–2.0"
    )
    max_tokens: Optional[int] = Field(
        default=None, ge=1, le=128000,
        description="Maximum tokens to generate, 1–128000"
    )
    theme: Optional[str] = None
    language: Optional[str] = None
    auto_save: Optional[bool] = None
    streaming: Optional[bool] = None
    backend_port: Optional[int] = None


@router.get("/api/config")
async def get_config():
    """Return the current configuration."""
    return _config


@router.put("/api/config")
async def update_config(body: ConfigUpdate):
    """Update configuration values."""
    updates = body.model_dump(exclude_none=True)
    _config.update(updates)
    return _config
