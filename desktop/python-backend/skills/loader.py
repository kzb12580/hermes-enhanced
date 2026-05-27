"""Skill loader — parses .md skill files with YAML frontmatter."""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import yaml


@dataclass
class Skill:
    """Represents a single loaded skill."""
    name: str
    description: str
    category: str
    tags: List[str]
    triggers: List[str]
    tools: List[str]
    priority: int
    content: str          # Full Markdown content (including frontmatter)
    is_builtin: bool
    path: str


class SkillLoader:
    """Discovers, parses, and indexes skill definition files (.md with YAML frontmatter)."""

    def __init__(self, builtin_dir: str = None, user_dir: str = None):
        self.builtin_dir = builtin_dir or os.path.join(os.path.dirname(__file__), "builtin")
        self.user_dir = user_dir or os.path.expanduser("~/.hermes-desktop/skills")
        self.skills: Dict[str, Skill] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Load skills from both built-in and user directories."""
        self._load_from_dir(self.builtin_dir, is_builtin=True)
        if os.path.exists(self.user_dir):
            self._load_from_dir(self.user_dir, is_builtin=False)

    def _load_from_dir(self, directory: str, is_builtin: bool) -> None:
        """Iterate over *.md files in *directory* and parse each one."""
        for file_path in sorted(Path(directory).glob("*.md")):
            try:
                skill = self._parse_skill(file_path, is_builtin)
                if skill:
                    self.skills[skill.name] = skill
            except Exception as exc:
                print(f"[SkillLoader] Error loading {file_path}: {exc}")

    @staticmethod
    def _parse_skill(file_path: Path, is_builtin: bool) -> Optional[Skill]:
        """Parse a single Markdown skill file that starts with YAML frontmatter."""
        content = file_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
        if not match:
            return None

        yaml_str, _markdown_body = match.groups()
        meta = yaml.safe_load(yaml_str) or {}

        return Skill(
            name=meta.get("name", file_path.stem),
            description=meta.get("description", "").strip(),
            category=meta.get("category", "general"),
            tags=meta.get("tags", []),
            triggers=meta.get("triggers", []),
            tools=meta.get("tools", []),
            priority=int(meta.get("priority", 5)),
            content=content,
            is_builtin=is_builtin,
            path=str(file_path),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[Skill]:
        """Return skills whose triggers / tags / name match *query* (case-insensitive)."""
        q = query.lower()
        results: List[Skill] = []
        for skill in self.skills.values():
            if any(t.lower() in q for t in skill.triggers):
                results.append(skill)
            elif any(t.lower() in q for t in skill.tags):
                results.append(skill)
            elif skill.name.lower() in q:
                results.append(skill)
        results.sort(key=lambda s: s.priority, reverse=True)
        return results

    def get_all(self) -> List[Skill]:
        """Return every loaded skill."""
        return list(self.skills.values())

    def get_by_name(self, name: str) -> Optional[Skill]:
        """Look up a single skill by its unique name."""
        return self.skills.get(name)

    def reload(self) -> None:
        """Drop all cached skills and re-scan directories."""
        self.skills.clear()
        self._load_all()
