"""Skill tools — save and reuse successful workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from .base import BaseTool
from . import register

SKILLS_DIR = Path.home() / ".hermes" / "desktop" / "skills"


def _sanitize_name(name: str) -> str:
    """净化 skill 名称，防止路径穿越"""
    import re
    sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '', name).lower()
    if not sanitized or sanitized.startswith('.'):
        raise ValueError(f"Invalid skill name: '{name}'")
    return sanitized


def _ensure_dir():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


class SaveSkillTool(BaseTool):
    name = "save_skill"
    description = "Save a successful workflow as a reusable skill. Use after completing a complex task that could be repeated. Include step-by-step instructions, commands, and pitfalls."
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name (lowercase, hyphens, e.g. 'create-report')"},
            "description": {"type": "string", "description": "What this skill does"},
            "steps": {"type": "string", "description": "Step-by-step instructions to reproduce this workflow"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization", "default": []},
        },
        "required": ["name", "description", "steps"],
    }

    async def execute(self, name: str, description: str, steps: str, tags: list = None, **kwargs) -> str:
        _ensure_dir()
        name = _sanitize_name(name)
        data = {
            "name": name,
            "description": description,
            "steps": steps,
            "tags": tags or [],
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }
        path = SKILLS_DIR / f"{name}.json"
        path.write_text(json.dumps(skill, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.dumps({"ok": True, "path": str(path), "name": name}, ensure_ascii=False)


class ListSkillsTool(BaseTool):
    name = "list_skills"
    description = "List all saved skills/workflows. Use to find reusable approaches for tasks."
    timeout = 5
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        _ensure_dir()
        skills = []
        for f in SKILLS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skills.append({
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "tags": data.get("tags", []),
                })
            except Exception:
                pass
        return json.dumps({"total": len(skills), "skills": skills}, ensure_ascii=False)


class LoadSkillTool(BaseTool):
    name = "load_skill"
    description = "Load a saved skill to see its full instructions. Use before executing a known workflow."
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name to load"},
        },
        "required": ["name"],
    }

    async def execute(self, name: str, **kwargs) -> str:
        name = _sanitize_name(name)
        path = SKILLS_DIR / f"{name}.json"
        if not path.exists():
            return json.dumps({"ok": False, "error": f"Skill '{name}' not found"}, ensure_ascii=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps({"ok": True, "skill": data}, ensure_ascii=False)


class DeleteSkillTool(BaseTool):
    name = "delete_skill"
    description = "Delete a saved skill."
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name to delete"},
        },
        "required": ["name"],
    }

    async def execute(self, name: str, **kwargs) -> str:
        name = _sanitize_name(name)
        path = SKILLS_DIR / f"{name}.json"
        if not path.exists():
            return json.dumps({"ok": False, "error": f"Skill '{name}' not found"}, ensure_ascii=False)
        path.unlink()
        return json.dumps({"ok": True, "deleted": name}, ensure_ascii=False)


register(SaveSkillTool())
register(ListSkillsTool())
register(LoadSkillTool())
register(DeleteSkillTool())
