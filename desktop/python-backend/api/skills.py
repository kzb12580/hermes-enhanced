"""Skills API — manage and query skills."""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.skills_manager import skill_manager

logger = logging.getLogger("hermes-backend.skills")
router = APIRouter()


@router.get("/api/skills")
async def list_skills():
    """List all available skills."""
    skills = skill_manager.get_all_skills()
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
            }
            for s in skills
        ]
    }


@router.get("/api/skills/{name}")
async def get_skill(name: str):
    """Get a specific skill by name."""
    skill = skill_manager.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {
        "name": skill.name,
        "description": skill.description,
        "triggers": skill.triggers,
        "content": skill.content,
    }


class SkillQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)


@router.post("/api/skills/match")
async def match_skills(request: SkillQuery):
    """Find skills matching a query."""
    skills = skill_manager.get_skills_for_query(request.query)
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
            }
            for s in skills
        ]
    }
