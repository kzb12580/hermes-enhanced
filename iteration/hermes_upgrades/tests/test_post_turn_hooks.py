"""Tests for post_turn_hooks.py"""

import asyncio
import pytest
import sys
import os

# Ensure package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hermes_upgrades.post_turn_hooks import (
    HookContext,
    HookResult,
    PostTurnHook,
    MemoryExtractionHook,
    UsageTrackingHook,
    PromptSuggestionHook,
    ContextHealthHook,
    HookPipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SimpleHook(PostTurnHook):
    """A trivial hook for pipeline tests."""

    def __init__(self, name: str, priority: int = 100):
        self.name = name
        self.priority = priority

    async def execute(self, ctx: HookContext) -> HookResult:
        return HookResult(hook_name=self.name, success=True, data={"ran": True})


class _BrokenHook(PostTurnHook):
    """A hook that always raises."""

    name = "broken"
    priority = 999

    async def execute(self, ctx: HookContext) -> HookResult:
        raise RuntimeError("hook exploded")


# ---------------------------------------------------------------------------
# 1. HookContext creation
# ---------------------------------------------------------------------------


def test_hook_context_defaults():
    ctx = HookContext()
    assert ctx.messages == []
    assert ctx.user_message == ""
    assert ctx.assistant_message == ""
    assert ctx.tool_calls == []
    assert ctx.tool_results == []
    assert ctx.session_id == ""
    assert ctx.turn_number == 0


def test_hook_context_with_values():
    ctx = HookContext(
        messages=[{"role": "user", "content": "hi"}],
        user_message="hi",
        assistant_message="hello",
        tool_calls=[{"name": "read_file"}],
        tool_results=[{"content": "file content"}],
        session_id="abc",
        turn_number=5,
    )
    assert len(ctx.messages) == 1
    assert ctx.user_message == "hi"
    assert ctx.assistant_message == "hello"
    assert len(ctx.tool_calls) == 1
    assert len(ctx.tool_results) == 1
    assert ctx.session_id == "abc"
    assert ctx.turn_number == 5


# ---------------------------------------------------------------------------
# 2. HookResult fields
# ---------------------------------------------------------------------------


def test_hook_result_defaults():
    r = HookResult(hook_name="test", success=True)
    assert r.hook_name == "test"
    assert r.success is True
    assert r.data == {}
    assert r.elapsed_ms == 0.0
    assert r.error is None


def test_hook_result_with_all_fields():
    r = HookResult(
        hook_name="x",
        success=False,
        data={"key": "val"},
        elapsed_ms=12.5,
        error="oops",
    )
    assert r.hook_name == "x"
    assert r.success is False
    assert r.data == {"key": "val"}
    assert r.elapsed_ms == 12.5
    assert r.error == "oops"


# ---------------------------------------------------------------------------
# 3. MemoryExtractionHook
# ---------------------------------------------------------------------------


def test_memory_extraction_finds_preference():
    ctx = HookContext(user_message="I prefer dark mode in all my editors")
    hook = MemoryExtractionHook()
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["memories_found"] >= 1
    types = [e["type"] for e in result.data["entries"]]
    assert "user" in types


def test_memory_extraction_finds_remember():
    ctx = HookContext(user_message="Remember that my birthday is June 5th")
    hook = MemoryExtractionHook()
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["memories_found"] >= 1
    # Should also hit the extra "please remember" pattern via "remember" in MemoryExtractor
    assert any(e["type"] == "user" for e in result.data["entries"])


def test_memory_extraction_extra_pattern_note_that():
    ctx = HookContext(user_message="Note that the server runs on port 8080")
    hook = MemoryExtractionHook()
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert len(result.data["extra_pattern_hits"]) >= 1


def test_memory_extraction_no_match():
    ctx = HookContext(user_message="What is the weather today?")
    hook = MemoryExtractionHook()
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["memories_found"] == 0
    assert result.data["entries"] == []
    assert result.data["extra_pattern_hits"] == []


# ---------------------------------------------------------------------------
# 4. UsageTrackingHook
# ---------------------------------------------------------------------------


def test_usage_tracking_counts_tools():
    hook = UsageTrackingHook()
    ctx = HookContext(
        user_message="Hello there, this is a test message",  # ~9 tokens
        assistant_message="Sure, I can help with that request",  # ~9 tokens
        tool_calls=[{"name": "a"}, {"name": "b"}, {"name": "c"}],
        tool_results=[{"content": "result1"}, {"content": "result2"}],
    )
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["turn_tool_calls"] == 3
    assert result.data["turn_tool_results"] == 2
    assert result.data["turn_tokens_est"] > 0
    assert result.data["cumulative"]["total_turns"] == 1
    assert result.data["cumulative"]["total_tool_calls"] == 3


def test_usage_tracking_cumulative():
    hook = UsageTrackingHook()
    ctx1 = HookContext(user_message="hi", tool_calls=[{"name": "a"}])
    ctx2 = HookContext(user_message="hello", tool_calls=[{"name": "b"}, {"name": "c"}])
    asyncio.run(hook.execute(ctx1))
    result2 = asyncio.run(hook.execute(ctx2))
    assert result2.data["cumulative"]["total_turns"] == 2
    assert result2.data["cumulative"]["total_tool_calls"] == 3


# ---------------------------------------------------------------------------
# 5. PromptSuggestionHook
# ---------------------------------------------------------------------------


def test_prompt_suggestion_edit_suggests_tests():
    hook = PromptSuggestionHook()
    ctx = HookContext(
        tool_calls=[{"name": "write_file", "arguments": {"path": "/tmp/foo.py"}}],
        user_message="Fix the bug",
    )
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["edited_files"] == ["/tmp/foo.py"]
    assert any("tests" in s.lower() or "linting" in s.lower() for s in result.data["suggestions"])


def test_prompt_suggestion_error_suggests_debug():
    hook = PromptSuggestionHook()
    ctx = HookContext(
        tool_results=[{"content": "Traceback (most recent call last): ..."}],
        user_message="Run the script",
    )
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["has_error"] is True
    assert any("debug" in s.lower() or "error" in s.lower() for s in result.data["suggestions"])


def test_prompt_suggestion_no_suggestions_for_plain():
    hook = PromptSuggestionHook()
    ctx = HookContext(
        user_message="Tell me a joke",
        assistant_message="Why did the chicken cross the road?",
    )
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    # No tool calls, no errors, no edits → should have zero or one suggestion (question check)
    # user message doesn't end with ?, so no suggestions
    assert result.data["suggestions"] == []


def test_prompt_suggestion_question_mark():
    hook = PromptSuggestionHook()
    ctx = HookContext(user_message="How does this work?")
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert any("question" in s.lower() for s in result.data["suggestions"])


# ---------------------------------------------------------------------------
# 6. ContextHealthHook
# ---------------------------------------------------------------------------


def test_context_health_low_pressure():
    # model_token_limit=1000, small message → pressure < 0.5 → "healthy"
    hook = ContextHealthHook(model_token_limit=1000)
    ctx = HookContext(messages=[{"role": "user", "content": "hi"}])  # ~12 tokens
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["health"] == "healthy"
    assert result.data["warning"] is None


def test_context_health_high_pressure():
    # model_token_limit=1000, large message → pressure ≥ 0.95 → "critical"
    hook = ContextHealthHook(model_token_limit=1000)
    big_content = "x" * 3800  # ~950 tokens + 10 overhead = 960, 960/1000 = 0.96
    ctx = HookContext(messages=[{"role": "user", "content": big_content}])
    result = asyncio.run(hook.execute(ctx))
    assert result.success is True
    assert result.data["health"] == "critical"
    assert result.data["warning"] is not None
    assert "immediate compression" in result.data["warning"].lower()


# ---------------------------------------------------------------------------
# 7. HookPipeline
# ---------------------------------------------------------------------------


def test_pipeline_register_and_get():
    pipeline = HookPipeline()
    h = _SimpleHook("a", priority=10)
    pipeline.register(h)
    hooks = pipeline.get_hooks()
    assert len(hooks) == 1
    assert hooks[0]["name"] == "a"
    assert hooks[0]["priority"] == 10
    assert hooks[0]["enabled"] is True


def test_pipeline_register_replaces_same_name():
    pipeline = HookPipeline()
    h1 = _SimpleHook("a", priority=10)
    h2 = _SimpleHook("a", priority=20)
    pipeline.register(h1)
    pipeline.register(h2)
    hooks = pipeline.get_hooks()
    assert len(hooks) == 1
    assert hooks[0]["priority"] == 20  # replaced


def test_pipeline_unregister():
    pipeline = HookPipeline()
    pipeline.register(_SimpleHook("a"))
    assert pipeline.unregister("a") is True
    assert pipeline.get_hooks() == []
    assert pipeline.unregister("nonexistent") is False


def test_pipeline_run_all_priority_order():
    pipeline = HookPipeline()
    h_high = _SimpleHook("last", priority=200)
    h_low = _SimpleHook("first", priority=10)
    pipeline.register(h_high)
    pipeline.register(h_low)
    ctx = HookContext()
    results = asyncio.run(pipeline.run_all(ctx))
    assert len(results) == 2
    assert results[0].hook_name == "first"
    assert results[1].hook_name == "last"


def test_pipeline_enable_disable():
    pipeline = HookPipeline()
    h = _SimpleHook("a")
    pipeline.register(h)
    pipeline.set_enabled("a", False)
    ctx = HookContext()
    results = asyncio.run(pipeline.run_all(ctx))
    assert len(results) == 0  # disabled hook skipped
    pipeline.set_enabled("a", True)
    results = asyncio.run(pipeline.run_all(ctx))
    assert len(results) == 1


def test_pipeline_set_enabled_nonexistent():
    pipeline = HookPipeline()
    assert pipeline.set_enabled("nope", False) is False


def test_pipeline_constructor_with_hooks():
    h1 = _SimpleHook("a", priority=20)
    h2 = _SimpleHook("b", priority=10)
    pipeline = HookPipeline(hooks=[h1, h2])
    hooks = pipeline.get_hooks()
    assert len(hooks) == 2
    assert hooks[0]["name"] == "b"  # lower priority first
    assert hooks[1]["name"] == "a"


# ---------------------------------------------------------------------------
# 8. Error handling
# ---------------------------------------------------------------------------


def test_pipeline_continues_on_hook_error():
    """Pipeline should continue running other hooks even if one raises."""
    pipeline = HookPipeline()
    pipeline.register(_BrokenHook())
    pipeline.register(_SimpleHook("good", priority=10))
    ctx = HookContext()
    # After the fix, broken hooks return a failure result instead of propagating
    results = asyncio.run(pipeline.run_all(ctx))
    # Both hooks should have results
    assert len(results) == 2
    # The broken hook should have a failure result
    broken_result = [r for r in results if r.hook_name == "broken"][0]
    assert not broken_result.success
    assert "hook exploded" in broken_result.error
    # The good hook should succeed
    good_result = [r for r in results if r.hook_name == "good"][0]
    assert good_result.success


def test_builtin_hook_error_returns_failure_result():
    """Built-in hooks catch exceptions and return a failure HookResult."""
    hook = UsageTrackingHook()
    # Set user_message to an int to trigger TypeError in len(ctx.user_message)
    ctx = HookContext(user_message=42)  # type: ignore
    result = asyncio.run(hook.execute(ctx))
    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------------
# 9. run_selected
# ---------------------------------------------------------------------------


def test_run_selected_runs_only_named_hooks():
    pipeline = HookPipeline()
    pipeline.register(_SimpleHook("a", priority=10))
    pipeline.register(_SimpleHook("b", priority=20))
    pipeline.register(_SimpleHook("c", priority=30))
    ctx = HookContext()
    results = asyncio.run(pipeline.run_selected(["a", "c"], ctx))
    names = [r.hook_name for r in results]
    assert names == ["a", "c"]
    assert "b" not in names


def test_run_selected_skips_disabled():
    pipeline = HookPipeline()
    h = _SimpleHook("a")
    pipeline.register(h)
    pipeline.set_enabled("a", False)
    ctx = HookContext()
    results = asyncio.run(pipeline.run_selected(["a"], ctx))
    assert len(results) == 0


def test_run_selected_nonexistent_name():
    pipeline = HookPipeline()
    pipeline.register(_SimpleHook("a"))
    ctx = HookContext()
    results = asyncio.run(pipeline.run_selected(["nonexistent"], ctx))
    assert len(results) == 0


def test_run_selected_preserves_priority_order():
    pipeline = HookPipeline()
    pipeline.register(_SimpleHook("z", priority=300))
    pipeline.register(_SimpleHook("m", priority=200))
    pipeline.register(_SimpleHook("a", priority=100))
    ctx = HookContext()
    results = asyncio.run(pipeline.run_selected(["z", "a"], ctx))
    names = [r.hook_name for r in results]
    assert names == ["a", "z"]  # priority order, not request order
