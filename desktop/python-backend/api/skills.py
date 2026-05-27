"""Skills API — list, view, search, and reload skills from Markdown files."""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ---------------------------------------------------------------------------
# Lazy singleton for the SkillLoader
# ---------------------------------------------------------------------------

_skill_loader = None


def get_skill_loader():
    global _skill_loader
    if _skill_loader is None:
        from skills.loader import SkillLoader
        _skill_loader = SkillLoader()
    return _skill_loader


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SkillInfo(BaseModel):
    name: str
    description: str
    category: str
    tags: List[str]
    triggers: List[str]
    is_builtin: bool


class SkillDetail(SkillInfo):
    content: str
    tools: List[str]


class SearchRequest(BaseModel):
    query: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/skills", response_model=List[SkillInfo])
async def list_skills():
    """Return all registered skills."""
    loader = get_skill_loader()
    return [
        SkillInfo(
            name=s.name,
            description=s.description,
            category=s.category,
            tags=s.tags,
            triggers=s.triggers,
            is_builtin=s.is_builtin,
        )
        for s in loader.get_all()
    ]


@router.get("/api/skills/{name}", response_model=SkillDetail)
async def get_skill(name: str):
    """Return full details for a single skill."""
    loader = get_skill_loader()
    skill = loader.get_by_name(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return SkillDetail(
        name=skill.name,
        description=skill.description,
        category=skill.category,
        tags=skill.tags,
        triggers=skill.triggers,
        tools=skill.tools,
        content=skill.content,
        is_builtin=skill.is_builtin,
    )


@router.post("/api/skills/search", response_model=List[SkillInfo])
async def search_skills(request: SearchRequest):
    """Search skills by keyword."""
    loader = get_skill_loader()
    return [
        SkillInfo(
            name=s.name,
            description=s.description,
            category=s.category,
            tags=s.tags,
            triggers=s.triggers,
            is_builtin=s.is_builtin,
        )
        for s in loader.search(request.query)
    ]


@router.post("/api/skills/reload")
async def reload_skills():
    """Re-scan skill directories and reload all definitions."""
    loader = get_skill_loader()
    loader.reload()
    return {"status": "ok", "count": len(loader.skills)}
