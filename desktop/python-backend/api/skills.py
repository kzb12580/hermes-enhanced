"""Skills API — list, view, create, update skills."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# In-memory skill store
_skills: dict[str, dict] = {
    "web-search": {
        "name": "web-search",
        "description": "Search the web for information",
        "enabled": True,
        "parameters": {"query": "string"},
    },
    "code-execution": {
        "name": "code-execution",
        "description": "Execute code in a sandboxed environment",
        "enabled": True,
        "parameters": {"language": "string", "code": "string"},
    },
}


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    parameters: dict = {}


class SkillUpdate(BaseModel):
    description: Optional[str] = None
    enabled: Optional[bool] = None
    parameters: Optional[dict] = None


@router.get("/api/skills")
async def list_skills():
    """Return all registered skills."""
    return list(_skills.values())


@router.get("/api/skills/{name}")
async def get_skill(name: str):
    """Return details for a single skill."""
    if name not in _skills:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return _skills[name]


@router.post("/api/skills")
async def create_skill(body: SkillCreate):
    """Register a new skill."""
    if body.name in _skills:
        raise HTTPException(status_code=409, detail="Skill already exists")
    _skills[body.name] = body.model_dump()
    return _skills[body.name]


@router.put("/api/skills/{name}")
async def update_skill(name: str, body: SkillUpdate):
    """Update an existing skill."""
    if name not in _skills:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    updates = body.model_dump(exclude_none=True)
    _skills[name].update(updates)
    return _skills[name]
