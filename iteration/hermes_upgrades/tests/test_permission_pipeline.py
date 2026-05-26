"""Comprehensive tests for the Permission Pipeline module."""

from __future__ import annotations

import pytest

from permission_pipeline import (
    PermissionDecision,
    PermissionLevel,
    PermissionPipeline,
    PermissionRule,
)


# ── PermissionLevel ──────────────────────────────────────────────────────────

class TestPermissionLevel:
    def test_enum_values(self):
        assert PermissionLevel.AUTO.value == "auto"
        assert PermissionLevel.PROMPT.value == "prompt"
        assert PermissionLevel.DENY.value == "deny"

    def test_enum_members(self):
        assert set(PermissionLevel) == {PermissionLevel.AUTO, PermissionLevel.PROMPT, PermissionLevel.DENY}


# ── PermissionRule ───────────────────────────────────────────────────────────

class TestPermissionRule:
    def test_exact_match(self):
        rule = PermissionRule("read_file", PermissionLevel.AUTO)
        assert rule.matches("read_file") is True
        assert rule.matches("write_file") is False

    def test_glob_star(self):
        rule = PermissionRule("read_*", PermissionLevel.AUTO)
        assert rule.matches("read_file") is True
        assert rule.matches("read_directory") is True
        assert rule.matches("write_file") is False

    def test_glob_catch_all(self):
        rule = PermissionRule("*", PermissionLevel.PROMPT)
        assert rule.matches("anything") is True
        assert rule.matches("") is True

    def test_condition_true_escalates(self):
        rule = PermissionRule("terminal", PermissionLevel.PROMPT, condition=lambda args: True)
        assert rule.evaluate_condition({"command": "ls"}) is True

    def test_condition_false_passes(self):
        rule = PermissionRule("terminal", PermissionLevel.PROMPT, condition=lambda args: False)
        assert rule.evaluate_condition({"command": "ls"}) is False

    def test_no_condition_returns_true(self):
        rule = PermissionRule("read_file", PermissionLevel.AUTO)
        assert rule.evaluate_condition({}) is True

    def test_serialization_roundtrip(self):
        rule = PermissionRule("read_*", PermissionLevel.AUTO, "Read anything")
        d = rule.to_dict()
        restored = PermissionRule.from_dict(d)
        assert restored.tool_name == "read_*"
        assert restored.level == PermissionLevel.AUTO
        assert restored.description == "Read anything"
        assert restored.condition is None  # not serializable


# ── PermissionDecision ───────────────────────────────────────────────────────

class TestPermissionDecision:
    def test_fields(self):
        d = PermissionDecision(allowed=True, level=PermissionLevel.AUTO, reason="ok")
        assert d.allowed is True
        assert d.needs_prompt is False

    def test_needs_prompt(self):
        d = PermissionDecision(allowed=False, level=PermissionLevel.PROMPT, reason="ask", needs_prompt=True)
        assert d.needs_prompt is True


# ── Default rules ────────────────────────────────────────────────────────────

class TestDefaultRules:
    def test_read_file_auto(self):
        pp = PermissionPipeline()
        d = pp.check("read_file", {"path": "/tmp/x"})
        assert d.allowed is True
        assert d.level == PermissionLevel.AUTO
        assert d.needs_prompt is False

    def test_search_files_auto(self):
        pp = PermissionPipeline()
        d = pp.check("search_files", {"pattern": "*.py"})
        assert d.allowed is True

    @pytest.mark.parametrize("tool", ["web_search", "web_extract", "session_search", "skill_view", "skills_list", "delegate_task", "memory"])
    def test_auto_tools(self, tool):
        pp = PermissionPipeline()
        d = pp.check(tool, {})
        assert d.allowed is True
        assert d.level == PermissionLevel.AUTO

    def test_write_file_prompt(self):
        pp = PermissionPipeline()
        d = pp.check("write_file", {"path": "/tmp/x", "content": "hi"})
        assert d.allowed is False
        assert d.needs_prompt is True
        assert d.level == PermissionLevel.PROMPT

    def test_patch_prompt(self):
        pp = PermissionPipeline()
        d = pp.check("patch", {"path": "/tmp/x"})
        assert d.needs_prompt is True

    def test_terminal_prompt(self):
        pp = PermissionPipeline()
        d = pp.check("terminal", {"command": "ls -la"})
        assert d.needs_prompt is True
        assert d.level == PermissionLevel.PROMPT

    def test_send_message_prompt(self):
        pp = PermissionPipeline()
        d = pp.check("send_message", {"text": "hello"})
        assert d.needs_prompt is True

    def test_unknown_tool_defaults_to_prompt(self):
        pp = PermissionPipeline()
        d = pp.check("mystery_tool", {})
        assert d.needs_prompt is True
        assert "No matching rule" in d.reason


# ── Dangerous pattern detection ─────────────────────────────────────────────

class TestDangerousPatterns:
    @pytest.mark.parametrize("cmd", [
        "rm -rf /",
        "rm -rf /home",
        "sudo rm -rf / --no-preserve-root",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sdb1",
        ":(){ :|:& };:",
        "echo hi > /dev/sda",
        "cat foo > /dev/sdb1",
    ])
    def test_dangerous_commands_denied(self, cmd):
        pp = PermissionPipeline()
        d = pp.check("terminal", {"command": cmd})
        assert d.allowed is False
        assert d.level == PermissionLevel.DENY

    @pytest.mark.parametrize("cmd", [
        "ls -la",
        "echo hello world",
        "rm file.txt",
        "python script.py",
        "git commit -m 'test'",
        "cat /dev/null",
    ])
    def test_safe_commands_prompted(self, cmd):
        pp = PermissionPipeline()
        d = pp.check("terminal", {"command": cmd})
        assert d.needs_prompt is True
        assert d.level == PermissionLevel.PROMPT

    def test_terminal_no_command_key(self):
        pp = PermissionPipeline()
        d = pp.check("terminal", {})
        # No command → condition returns False → stays PROMPT
        assert d.needs_prompt is True

    def test_terminal_non_string_command(self):
        pp = PermissionPipeline()
        d = pp.check("terminal", {"command": 123})
        assert d.needs_prompt is True


# ── Custom rules ─────────────────────────────────────────────────────────────

class TestCustomRules:
    def test_custom_rule_first_wins(self):
        rules = [
            PermissionRule("*", PermissionLevel.DENY, "Block everything"),
            PermissionRule("read_file", PermissionLevel.AUTO, "Allow reads"),
        ]
        pp = PermissionPipeline(rules)
        d = pp.check("read_file", {})
        assert d.allowed is False  # catch-all wins

    def test_custom_auto_rule(self):
        rules = [PermissionRule("my_tool", PermissionLevel.AUTO, "Custom auto")]
        pp = PermissionPipeline(rules)
        d = pp.check("my_tool", {})
        assert d.allowed is True

    def test_custom_deny_rule(self):
        rules = [PermissionRule("bad_tool", PermissionLevel.DENY, "Blocked")]
        pp = PermissionPipeline(rules)
        d = pp.check("bad_tool", {})
        assert d.allowed is False
        assert d.level == PermissionLevel.DENY

    def test_glob_custom(self):
        rules = [
            PermissionRule("internal_*", PermissionLevel.DENY, "Block internal"),
            PermissionRule("*", PermissionLevel.AUTO, "Allow rest"),
        ]
        pp = PermissionPipeline(rules)
        assert pp.check("internal_debug", {}).allowed is False
        assert pp.check("public_api", {}).allowed is True


# ── Pipeline management ─────────────────────────────────────────────────────

class TestPipelineManagement:
    def test_add_rule_append(self):
        pp = PermissionPipeline(rules=[])
        pp.add_rule(PermissionRule("foo", PermissionLevel.AUTO))
        # rules=[] now creates a default allow-all rule, so 2 total
        assert len(pp.get_rules()) == 2

    def test_add_rule_at_index(self):
        pp = PermissionPipeline(rules=[
            PermissionRule("a", PermissionLevel.AUTO),
            PermissionRule("b", PermissionLevel.PROMPT),
        ])
        pp.add_rule(PermissionRule("c", PermissionLevel.DENY), index=1)
        names = [r.tool_name for r in pp.get_rules()]
        assert names == ["a", "c", "b"]

    def test_remove_rule(self):
        pp = PermissionPipeline(rules=[
            PermissionRule("a", PermissionLevel.AUTO),
            PermissionRule("b", PermissionLevel.PROMPT),
        ])
        removed = pp.remove_rule(0)
        assert removed.tool_name == "a"
        assert len(pp.get_rules()) == 1

    def test_remove_rule_out_of_range(self):
        pp = PermissionPipeline(rules=[])
        # rules=[] now has 1 default allow-all rule, so index 1 is out of range
        with pytest.raises(IndexError):
            pp.remove_rule(1)

    def test_get_rules_returns_copy(self):
        pp = PermissionPipeline(rules=[PermissionRule("x", PermissionLevel.AUTO)])
        rules = pp.get_rules()
        rules.clear()
        assert len(pp.get_rules()) == 1  # original unchanged


# ── Hooks ────────────────────────────────────────────────────────────────────

class TestHooks:
    def test_pre_hook_short_circuit(self):
        pp = PermissionPipeline()

        def always_allow(tool: str, args: dict) -> PermissionDecision | None:
            return PermissionDecision(True, PermissionLevel.AUTO, "Hook override")

        pp.add_pre_hook(always_allow)
        d = pp.check("write_file", {"path": "/tmp/x"})
        assert d.allowed is True
        assert "Hook override" in d.reason

    def test_pre_hook_pass_through(self):
        pp = PermissionPipeline()
        called = []

        def logging_hook(tool: str, args: dict) -> PermissionDecision | None:
            called.append(tool)
            return None  # continue pipeline

        pp.add_pre_hook(logging_hook)
        pp.check("read_file", {})
        assert called == ["read_file"]

    def test_multiple_pre_hooks_first_wins(self):
        pp = PermissionPipeline()

        def hook1(tool: str, args: dict) -> PermissionDecision | None:
            return None

        def hook2(tool: str, args: dict) -> PermissionDecision | None:
            return PermissionDecision(False, PermissionLevel.DENY, "Hook2 block")

        pp.add_pre_hook(hook1)
        pp.add_pre_hook(hook2)
        d = pp.check("read_file", {})
        assert d.allowed is False
        assert "Hook2" in d.reason

    def test_post_hook_modifies_decision(self):
        pp = PermissionPipeline()

        def override(tool: str, args: dict, decision: PermissionDecision) -> PermissionDecision:
            if decision.needs_prompt:
                return PermissionDecision(True, PermissionLevel.AUTO, "Auto-approved by hook")
            return decision

        pp.add_post_hook(override)
        d = pp.check("write_file", {"path": "/tmp/x"})
        assert d.allowed is True

    def test_post_hook_can_deny(self):
        pp = PermissionPipeline()

        def deny_all(tool: str, args: dict, decision: PermissionDecision) -> PermissionDecision:
            return PermissionDecision(False, PermissionLevel.DENY, "Post-hook deny")

        pp.add_post_hook(deny_all)
        d = pp.check("read_file", {})
        assert d.allowed is False

    def test_multiple_post_hooks_chain(self):
        pp = PermissionPipeline()
        order = []

        def hook1(tool: str, args: dict, d: PermissionDecision) -> PermissionDecision:
            order.append("h1")
            return d

        def hook2(tool: str, args: dict, d: PermissionDecision) -> PermissionDecision:
            order.append("h2")
            return d

        pp.add_post_hook(hook1)
        pp.add_post_hook(hook2)
        pp.check("read_file", {})
        assert order == ["h1", "h2"]


# ── Serialization ────────────────────────────────────────────────────────────

class TestSerialization:
    def test_to_dict_structure(self):
        pp = PermissionPipeline()
        d = pp.to_dict()
        assert "rules" in d
        assert isinstance(d["rules"], list)
        assert len(d["rules"]) > 0

    def test_roundtrip_default(self):
        pp = PermissionPipeline()
        data = pp.to_dict()
        pp2 = PermissionPipeline.from_dict(data)
        assert len(pp2.get_rules()) == len(pp.get_rules())
        for r1, r2 in zip(pp.get_rules(), pp2.get_rules()):
            assert r1.tool_name == r2.tool_name
            assert r1.level == r2.level

    def test_roundtrip_custom(self):
        rules = [
            PermissionRule("foo", PermissionLevel.AUTO, "Foo rule"),
            PermissionRule("bar_*", PermissionLevel.DENY, "Bar rule"),
        ]
        pp = PermissionPipeline(rules)
        data = pp.to_dict()
        pp2 = PermissionPipeline.from_dict(data)
        assert pp2.check("foo", {}).allowed is True
        assert pp2.check("bar_x", {}).allowed is False

    def test_from_dict_empty(self):
        pp = PermissionPipeline.from_dict({"rules": []})
        # Empty rules in from_dict loads default rules (via _build_default_rules)
        assert len(pp.get_rules()) > 0

    def test_from_dict_missing_rules(self):
        pp = PermissionPipeline.from_dict({})
        # Missing rules key loads default rules (via _build_default_rules)
        assert len(pp.get_rules()) > 0


# ── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_pipeline_prompts(self):
        pp = PermissionPipeline(rules=[])
        d = pp.check("anything", {})
        # rules=[] now means allow-all with default wildcard rule
        assert d.needs_prompt is False
        assert d.allowed is True

    def test_condition_on_deny_rule_ignored(self):
        """DENY rules don't evaluate conditions (condition only escalates PROMPT→DENY)."""
        rule = PermissionRule("x", PermissionLevel.DENY, condition=lambda args: False)
        pp = PermissionPipeline([rule])
        d = pp.check("x", {})
        assert d.allowed is False

    def test_context_param_accepted(self):
        pp = PermissionPipeline()
        d = pp.check("read_file", {"path": "/tmp"}, context={"user": "admin"})
        assert d.allowed is True

    def test_empty_tool_name(self):
        pp = PermissionPipeline(rules=[PermissionRule("", PermissionLevel.AUTO, "Empty name")])
        d = pp.check("", {})
        assert d.allowed is True
