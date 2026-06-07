"""Skill tools — save and reuse successful workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from .base import BaseTool
from . import register

SKILLS_DIR = Path.home() / ".hermes-desktop" / "skills"


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
    description = "将成功工作流保存为可复用技能。适用于完成可重复的复杂任务后，需包含步骤、命令和注意事项。"
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "技能名称（小写，可用连字符，例如 'create-report'）"},
            "description": {"type": "string", "description": "这个技能的用途说明"},
            "steps": {"type": "string", "description": "复现该工作流的逐步说明"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "分类标签", "default": []},
        },
        "required": ["name", "description", "steps"],
    }

    async def execute(self, name: str, description: str, steps: str, tags: list = None, **kwargs) -> str:
        _ensure_dir()
        name = _sanitize_name(name)
        # LLM may pass tags as a JSON string instead of a list
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, ValueError):
                tags = [tags]
        data = {
            "name": name,
            "description": description,
            "steps": steps,
            "tags": tags or [],
            "triggers": tags or [],  # 前端期望 triggers 字段
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }
        path = SKILLS_DIR / f"{name}.json"
        import tempfile, os
        fd, tmp = tempfile.mkstemp(dir=str(SKILLS_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(path))
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        # Refresh SkillManager cache so new skill is immediately available
        try:
            from api.skills_manager import skill_manager
            skill_manager.reload()
        except Exception:
            pass
        return json.dumps({"ok": True, "path": str(path), "name": name}, ensure_ascii=False)


class ListSkillsTool(BaseTool):
    name = "list_skills"
    description = "列出所有已保存技能/工作流，用于查找可复用的任务处理方法。"
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
    description = "加载已保存技能并查看完整说明。执行已知工作流前使用。"
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "要加载的技能名称"},
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
    description = "删除已保存技能。"
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "要删除的技能名称"},
        },
        "required": ["name"],
    }

    async def execute(self, name: str, **kwargs) -> str:
        name = _sanitize_name(name)
        path = SKILLS_DIR / f"{name}.json"
        if not path.exists():
            return json.dumps({"ok": False, "error": f"Skill '{name}' not found"}, ensure_ascii=False)
        path.unlink()
        # Refresh SkillManager cache
        try:
            from api.skills_manager import skill_manager
            skill_manager.reload()
        except Exception:
            pass
        return json.dumps({"ok": True, "deleted": name}, ensure_ascii=False)


