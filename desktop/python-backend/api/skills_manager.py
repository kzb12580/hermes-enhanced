"""Skills system — loadable skill packs for different domains."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes-backend.skills")

# Skills directory
_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class Skill:
    """Represents a loadable skill."""
    
    def __init__(self, name: str, description: str, triggers: list[str], content: str,
                 category: str = "general", tags: list[str] = None, tools: list[str] = None,
                 priority: int = 5, is_builtin: bool = True, path: str = ""):
        self.name = name
        self.description = description
        self.triggers = triggers
        self.content = content
        self.category = category
        self.tags = tags or []
        self.tools = tools or []
        self.priority = priority
        self.is_builtin = is_builtin
        self.path = path
    
    def to_context(self) -> str:
        """Convert skill to context string for system prompt."""
        return f"### Skill: {self.name}\n{self.description}\n\n{self.content}"


class SkillManager:
    """Manages available skills — loads from builtin .md files + hardcoded fallback."""
    
    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._load_from_files()
        # 如果文件加载失败，回退到硬编码技能
        if not self._skills:
            self._load_builtin_hardcoded()
        logger.info("Loaded %d skills total", len(self._skills))
    
    def _load_from_files(self):
        """Load skills from builtin/*.md files using SkillLoader."""
        try:
            from skills.loader import SkillLoader
            loader = SkillLoader(
                builtin_dir=str(_SKILLS_DIR / "builtin"),
                user_dir=str(Path.home() / ".hermes-desktop" / "skills"),
            )
            for skill_data in loader.get_all():
                self._skills[skill_data.name] = Skill(
                    name=skill_data.name,
                    description=skill_data.description,
                    triggers=skill_data.triggers,
                    content=skill_data.content,
                    category=skill_data.category,
                    tags=skill_data.tags,
                    tools=skill_data.tools,
                    priority=skill_data.priority,
                    is_builtin=skill_data.is_builtin,
                    path=skill_data.path,
                )
            logger.info("Loaded %d skills from files", len(self._skills))
        except Exception as e:
            logger.warning("Failed to load skills from files: %s", e)
    
    def _load_builtin_hardcoded(self):
        """Fallback: hardcoded skills if file loading fails."""
        builtin_skills = [
            Skill(
                name="code-review",
                description="Review code for quality, security, and best practices",
                triggers=["review", "check code", "audit", "code quality"],
                content="""## Code Review Process
1. Read the code carefully
2. Check for security, performance, style, error handling
3. Provide specific, actionable feedback"""
            ),
            Skill(
                name="debugging",
                description="Systematic debugging approach",
                triggers=["debug", "error", "bug", "fix", "issue"],
                content="""## Debugging Process
1. Reproduce — Understand how to trigger the bug
2. Isolate — Find the smallest code that reproduces it
3. Identify — Determine the root cause
4. Fix — Implement the minimal fix
5. Test — Verify the fix works"""
            ),
            Skill(
                name="data-analysis",
                description="Analyze data with pandas and visualization",
                triggers=["analyze", "data", "csv", "excel", "statistics"],
                content="""## Data Analysis Workflow
1. Load Data — Read CSV/Excel/JSON with pandas
2. Explore — Check shape, dtypes, missing values
3. Clean — Handle missing values, outliers
4. Analyze — Group, aggregate, correlate
5. Visualize — Create charts"""
            ),
            Skill(
                name="presentation",
                description="Create presentations with python-pptx",
                triggers=["ppt", "presentation", "slides"],
                content="""## Presentation Creation
Use python-pptx to create professional presentations."""
            ),
            Skill(
                name="web-scraping",
                description="Extract data from websites",
                triggers=["scrape", "extract", "web data"],
                content="""## Web Scraping
1. web_search to find relevant pages
2. web_extract to get content
3. Parse and structure the data"""
            ),
            Skill(
                name="file-organization",
                description="Organize files systematically",
                triggers=["organize", "clean up", "sort files"],
                content="""## File Organization
1. Inventory — List all files
2. Categorize — Group by type
3. Structure — Create folder hierarchy
4. Move — Relocate files"""
            ),
            Skill(
                name="research",
                description="Conduct thorough research",
                triggers=["research", "find information", "learn about"],
                content="""## Research Process
1. Define — Clarify what you need
2. Search — Use multiple queries
3. Evaluate — Check reliability
4. Synthesize — Combine findings"""
            ),
            Skill(
                name="excel-processing",
                description="Process Excel files with openpyxl",
                triggers=["excel", "xlsx", "spreadsheet"],
                content="""## Excel Processing
Use openpyxl to read/write Excel files."""
            ),
        ]
        
        for skill in builtin_skills:
            self._skills[skill.name] = skill
        
        logger.info("Loaded %d hardcoded fallback skills", len(builtin_skills))
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)
    
    def get_all_skills(self) -> list[Skill]:
        """Get all available skills."""
        return list(self._skills.values())
    
    def get_skills_for_query(self, query: str) -> list[Skill]:
        """Get skills that match a query."""
        query_lower = query.lower()
        matched = []
        for skill in self._skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    matched.append(skill)
                    break
            else:
                # 也检查 tags
                for tag in skill.tags:
                    if tag.lower() in query_lower:
                        matched.append(skill)
                        break
        return matched
    
    def get_skills_context(self, query: Optional[str] = None, active_skills: Optional[list[str]] = None) -> str:
        """Get skills context for system prompt."""
        if active_skills is not None:
            skills = [s for s in self._skills.values() if s.name in active_skills] if active_skills else []
        elif query:
            skills = self.get_skills_for_query(query)
        else:
            skills = self.get_all_skills()
        
        if not skills:
            return ""
        
        contexts = [skill.to_context() for skill in skills]
        return "\n\n".join(contexts)


# Global skill manager
skill_manager = SkillManager()
