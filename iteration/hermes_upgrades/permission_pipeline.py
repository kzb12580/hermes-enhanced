"""Permission Pipeline module for Hermes Agent.

A layered permission system inspired by Claude Code's architecture.
Provides glob-based tool matching, conditional rules, dangerous pattern
detection, and a hook system for pre/post permission processing.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class PermissionLevel(Enum):
    """Permission levels for tool invocations."""

    AUTO = "auto"
    PROMPT = "prompt"
    DENY = "deny"


@dataclass
class PermissionDecision:
    """Result of a permission check."""

    allowed: bool
    level: PermissionLevel
    reason: str
    needs_prompt: bool = False


@dataclass
class PermissionRule:
    """A rule matching tool names via glob patterns."""

    tool_name: str  # glob pattern, e.g. 'read_*', '*'
    level: PermissionLevel
    description: str = ""
    condition: Optional[Callable[[dict[str, Any]], bool]] = None

    def matches(self, tool_name: str) -> bool:
        """Check if this rule matches a given tool name."""
        return fnmatch.fnmatch(tool_name, self.tool_name)

    def evaluate_condition(self, args: dict[str, Any]) -> bool:
        """Evaluate the condition callable, if present. Returns True if no condition."""
        if self.condition is None:
            return True
        return self.condition(args)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (condition not serializable, omitted)."""
        return {
            "tool_name": self.tool_name,
            "level": self.level.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionRule:
        """Deserialize from dict."""
        return cls(
            tool_name=data["tool_name"],
            level=PermissionLevel(data["level"]),
            description=data.get("description", ""),
        )


# Pre-compiled dangerous pattern detection for terminal commands
_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    # Destructive file operations
    re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/"),
    re.compile(r"rm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s+/"),
    re.compile(r"\brm\s+-[a-zA-Z]*rf"),
    re.compile(r"\brmdir\s+/"),
    re.compile(r"dd\s+if="),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bfdisk\b"),
    # Fork bomb
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};\s*:"),
    # Disk/device writes
    re.compile(r">\s*/dev/sd"),
    re.compile(r">\s*/dev/nvme"),
    # Privilege escalation
    re.compile(r"\bsudo\b"),
    re.compile(r"\bsu\s+-"),
    # Pipe-to-shell attacks
    re.compile(r"\bcurl\b.*\|\s*(?:ba)?sh"),
    re.compile(r"\bwget\b.*\|\s*(?:ba)?sh"),
    re.compile(r"\bcurl\b.*\|\s*bash"),
    re.compile(r"\bwget\b.*\|\s*bash"),
    # Reverse shells / network backdoors
    re.compile(r"\bnc\s+-[a-zA-Z]*l"),
    re.compile(r"\bncat\b"),
    re.compile(r"\bnetcat\b"),
    re.compile(r"\bsocat\b"),
    # Dangerous permission changes
    re.compile(r"\bchmod\s+777"),
    re.compile(r"\bchmod\s+-R\s+777"),
    # Credential theft
    re.compile(r"\bcat\s+/etc/shadow"),
    re.compile(r"\bcat\s+/etc/passwd"),
    # Subshell / command substitution in dangerous context
    re.compile(r"\beval\s+"),
    # Environment variable exfiltration
    re.compile(r"\benv\b.*\|\s*(?:curl|wget|nc)"),
]


def _is_dangerous_command(args: dict[str, Any]) -> bool:
    """Check if terminal command contains dangerous patterns."""
    command = args.get("command", "")
    if not isinstance(command, str):
        return False
    return any(pat.search(command) for pat in _DANGEROUS_PATTERNS)


def _build_default_rules() -> list[PermissionRule]:
    """Build the default permission rules for Hermes Agent."""
    return [
        # Auto-approved tools
        PermissionRule("read_file", PermissionLevel.AUTO, "Allow reading files"),
        PermissionRule("search_files", PermissionLevel.AUTO, "Allow searching files"),
        PermissionRule("web_search", PermissionLevel.AUTO, "Allow web search"),
        PermissionRule("web_extract", PermissionLevel.AUTO, "Allow web extraction"),
        PermissionRule("session_search", PermissionLevel.AUTO, "Allow session search"),
        PermissionRule("skill_view", PermissionLevel.AUTO, "Allow skill viewing"),
        PermissionRule("skills_list", PermissionLevel.AUTO, "Allow listing skills"),
        PermissionRule("delegate_task", PermissionLevel.AUTO, "Allow task delegation"),
        PermissionRule("memory", PermissionLevel.AUTO, "Allow memory operations"),
        # Prompt-required tools
        PermissionRule("write_file", PermissionLevel.PROMPT, "Write operations require confirmation"),
        PermissionRule("patch", PermissionLevel.PROMPT, "Patch operations require confirmation"),
        PermissionRule(
            "terminal",
            PermissionLevel.PROMPT,
            "Terminal requires confirmation; dangerous commands are denied",
            condition=_is_dangerous_command,
        ),
        PermissionRule("send_message", PermissionLevel.PROMPT, "Sending messages requires confirmation"),
    ]


# Type aliases for hooks
PreHook = Callable[[str, dict[str, Any]], Optional[PermissionDecision]]
PostHook = Callable[[str, dict[str, Any], PermissionDecision], PermissionDecision]


class PermissionPipeline:
    """Multi-layer permission checking pipeline for tool invocations.

    Rules are evaluated in order; the first matching rule determines the
    decision. Pre-hooks can short-circuit the pipeline, and post-hooks
    can modify the final decision.
    """

    def __init__(self, rules: Optional[list[PermissionRule]] = None) -> None:
        """Initialize the pipeline with optional custom rules.

        Args:
            rules: List of permission rules. If None, default rules are used.
        """
        self.rules: list[PermissionRule] = rules if rules is not None else _build_default_rules()
        self.pre_hooks: list[PreHook] = []
        self.post_hooks: list[PostHook] = []

    def check(
        self, tool_name: str, args: dict[str, Any], context: dict[str, Any] | None = None
    ) -> PermissionDecision:
        """Check permission for a tool invocation.

        Evaluates pre-hooks first, then iterates rules in order (first match wins),
        and finally runs post-hooks which may modify the decision.

        Args:
            tool_name: Name of the tool being invoked.
            args: Arguments passed to the tool.
            context: Optional context dict (e.g. user info, session state).

        Returns:
            PermissionDecision describing the outcome.
        """
        # Run pre-hooks — any non-None result short-circuits
        for hook in self.pre_hooks:
            result = hook(tool_name, args)
            if result is not None:
                return result

        # Evaluate rules in order
        decision: Optional[PermissionDecision] = None
        for rule in self.rules:
            if rule.matches(tool_name):
                if rule.level == PermissionLevel.DENY:
                    decision = PermissionDecision(
                        allowed=False,
                        level=PermissionLevel.DENY,
                        reason=f"Blocked by rule: {rule.description or rule.tool_name}",
                        needs_prompt=False,
                    )
                elif rule.condition is not None and rule.evaluate_condition(args):
                    # Condition returned True → escalate to DENY
                    decision = PermissionDecision(
                        allowed=False,
                        level=PermissionLevel.DENY,
                        reason=f"Condition triggered for {tool_name}: {rule.description or 'dangerous pattern'}",
                        needs_prompt=False,
                    )
                elif rule.level == PermissionLevel.AUTO:
                    decision = PermissionDecision(
                        allowed=True,
                        level=PermissionLevel.AUTO,
                        reason=f"Auto-approved: {rule.description or rule.tool_name}",
                        needs_prompt=False,
                    )
                else:  # PROMPT
                    decision = PermissionDecision(
                        allowed=False,
                        level=PermissionLevel.PROMPT,
                        reason=f"Requires user confirmation: {rule.description or rule.tool_name}",
                        needs_prompt=True,
                    )
                break

        # No rule matched → default to PROMPT
        if decision is None:
            decision = PermissionDecision(
                allowed=False,
                level=PermissionLevel.PROMPT,
                reason=f"No matching rule for '{tool_name}'; defaulting to prompt",
                needs_prompt=True,
            )

        # Run post-hooks
        for hook in self.post_hooks:
            decision = hook(tool_name, args, decision)

        return decision

    def add_rule(self, rule: PermissionRule, index: Optional[int] = None) -> None:
        """Add a rule to the pipeline.

        Args:
            rule: The PermissionRule to add.
            index: Position to insert at. Appends if None.
        """
        if index is not None:
            self.rules.insert(index, rule)
        else:
            self.rules.append(rule)

    def remove_rule(self, index: int) -> PermissionRule:
        """Remove and return a rule by index.

        Args:
            index: Position of the rule to remove.

        Returns:
            The removed PermissionRule.

        Raises:
            IndexError: If index is out of range.
        """
        return self.rules.pop(index)

    def get_rules(self) -> list[PermissionRule]:
        """Return a copy of the current rules list."""
        return list(self.rules)

    def add_pre_hook(self, hook: PreHook) -> None:
        """Register a pre-hook that runs before permission evaluation."""
        self.pre_hooks.append(hook)

    def add_post_hook(self, hook: PostHook) -> None:
        """Register a post-hook that runs after permission evaluation."""
        self.post_hooks.append(hook)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the pipeline configuration to a dict.

        Note: Conditions and hooks are not serializable and are omitted.
        """
        return {
            "rules": [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionPipeline:
        """Deserialize a pipeline from a dict.

        Args:
            data: Dict with a "rules" key containing serialized rules.

        Returns:
            A new PermissionPipeline instance.
        """
        rules = [PermissionRule.from_dict(r) for r in data.get("rules", [])]
        return cls(rules=rules)
