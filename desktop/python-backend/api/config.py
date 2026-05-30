"""Config API — read and update application settings with persistence."""

import json
import logging
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("hermes-backend.config")
router = APIRouter()

# Config file path
_CONFIG_DIR = Path.home() / ".hermes-desktop"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# Allowed enum values for theme and language
_THEMES = {"light", "dark", "system"}
_LANGUAGES = {"en", "zh", "es", "fr", "de", "ja", "ko"}

# FIX #5: Use Literal types for theme and language
ThemeType = Literal["light", "dark", "system"]
LanguageType = Literal["en", "zh", "es", "fr", "de", "ja", "ko"]

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


def _load_config():
    """Load config from disk if available."""
    global _config
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            _config.update(saved)
            logger.info("Config loaded from %s", _CONFIG_FILE)
    except Exception as e:
        logger.warning("Failed to load config: %s", e)


def _save_config():
    """Save config to disk."""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Failed to save config: %s", e)


# Load on startup
_load_config()


class ConfigUpdate(BaseModel):
    # FIX: Add min_length/max_length to string fields
    model: Optional[str] = Field(default=None, min_length=1, max_length=200)
    temperature: Optional[float] = Field(
        default=None, ge=0.0, le=2.0,
        description="Sampling temperature, 0.0–2.0"
    )
    max_tokens: Optional[int] = Field(
        default=None, ge=1, le=128000,
        description="Maximum tokens to generate, 1–128000"
    )
    # FIX #5: Use Literal types instead of plain str for validation
    theme: Optional[ThemeType] = None
    language: Optional[LanguageType] = None
    auto_save: Optional[bool] = None
    streaming: Optional[bool] = None
    backend_port: Optional[int] = Field(
        default=None, ge=1024, le=65535,
        description="Backend port, 1024–65535"
    )


@router.get("/api/config")
async def get_config():
    """Return the current configuration."""
    return _config


@router.put("/api/config")
async def update_config(body: ConfigUpdate):
    """Update configuration values."""
    updates = body.model_dump(exclude_none=True)

    # With Literal types, Pydantic automatically validates theme and language,
    # so manual enum checks are no longer needed but kept as defense-in-depth
    if "theme" in updates and updates["theme"] not in _THEMES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid theme '{updates['theme']}'. Allowed: {sorted(_THEMES)}",
        )

    if "language" in updates and updates["language"] not in _LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid language '{updates['language']}'. Allowed: {sorted(_LANGUAGES)}",
        )

    _config.update(updates)
    _save_config()
    return _config
