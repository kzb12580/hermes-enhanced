"""Skills API — manage and query skills."""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.skills_manager import Skill, skill_manager

logger = logging.getLogger("hermes-backend.skills")
router = APIRouter()


def _skill_to_summary(skill: Skill) -> dict:
    """Serialize a skill for the skills list UI."""
    return {
        "id": skill.name,
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "tags": skill.tags,
        "triggers": skill.triggers,
        "is_builtin": skill.is_builtin,
        "tools": skill.tools,
        "enabled": True,
    }


def _skill_to_detail(skill: Skill) -> dict:
    """Serialize a skill with full content for the detail panel."""
    data = _skill_to_summary(skill)
    data["content"] = skill.content
    return data


@router.get("/api/skills")
async def list_skills():
    """List all available skills."""
    skills = skill_manager.get_all_skills()
    return [_skill_to_summary(skill) for skill in skills]


@router.get("/api/skills/{name}")
async def get_skill(name: str):
    """Get a specific skill by name."""
    skill = skill_manager.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return _skill_to_detail(skill)


class SkillQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)


@router.post("/api/skills/match")
async def match_skills(request: SkillQuery):
    """Find skills matching a query."""
    skills = skill_manager.get_skills_for_query(request.query)
    return [_skill_to_summary(skill) for skill in skills]


@router.post("/api/skills/reload")
async def reload_skills():
    """Reload all skills from disk."""
    try:
        skill_manager.reload()
        return {
            "status": "ok",
            "count": len(skill_manager.get_all_skills()),
            "skills": [s.name for s in skill_manager.get_all_skills()],
        }
    except Exception as e:
        logger.error("Failed to reload skills: %s", e)
        return {"success": False, "error": str(e)}
