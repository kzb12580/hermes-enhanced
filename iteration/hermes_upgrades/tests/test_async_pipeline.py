"""Tests for async_pipeline module."""

import asyncio
import sys
import os

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from async_pipeline import (
    BackPressureController,
    ContextWindow,
    Pipeline,
    PipelineStage,
    StreamingToolExecutor,
    ToolResult,
)


# ── helpers ──────────────────────────────────────────────────────────────

def run(coro):
    """Run an async coroutine to completion."""
    return asyncio.run(coro)


# ── PipelineStage ────────────────────────────────────────────────────────

def test_pipeline_stage_basic():
    async def double(x):
        yield x * 2

    stage = PipelineStage(name="dbl", process=double)
    assert stage.name == "dbl"
    assert stage.can_stream is True


def test_pipeline_stage_invocation():
    async def add_one(x):
        yield x + 1

    async def _run():
        stage = PipelineStage(name="inc", process=add_one)
        results = []
        async for r in stage(10):
            results.append(r)
        return results

    assert run(_run()) == [11]


# ── Pipeline ─────────────────────────────────────────────────────────────

def test_pipeline_empty():
    async def _run():
        p = Pipeline()
        out = []
        async for r in p.execute(42):
            out.append(r)
        return out

    assert run(_run()) == [42]


def test_pipeline_map():
    async def _run():
        p = Pipeline().map("double", lambda x: x * 2).map("add1", lambda x: x + 1)
        out = []
        async for r in p.execute(5):
            out.append(r)
        return out

    assert run(_run()) == [11]


def test_pipeline_filter():
    async def _run():
        p = Pipeline().filter("gt5", lambda x: x > 5)
        out = []
        for val in [3, 7, 1, 9]:
            async for r in p.execute(val):
                out.append(r)
        return out

    assert run(_run()) == [7, 9]


def test_pipeline_flat_map():
    async def _run():
        p = Pipeline().flat_map("explode", lambda x: [x, x + 1])
        out = []
        async for r in p.execute(10):
            out.append(r)
        return out

    assert run(_run()) == [10, 11]


def test_pipeline_chaining_returns_self():
    p = Pipeline()
    ret = p.map("a", lambda x: x)
    assert ret is p


def test_pipeline_multi_stage_composition():
    """Full pipeline: flat_map → map → filter."""
    async def _run():
        p = (
            Pipeline()
            .flat_map("range", lambda x: range(x))
            .map("sq", lambda x: x ** 2)
            .filter("big", lambda x: x > 10)
        )
        out = []
        async for r in p.execute(6):
            out.append(r)
        return out

    # range(6) = 0,1,2,3,4,5 → squares = 0,1,4,9,16,25 → filter >10 → [16,25]
    assert run(_run()) == [16, 25]


# ── StreamingToolExecutor ────────────────────────────────────────────────

def test_streaming_executor_completion_order():
    """Results should arrive in completion order, not submission order."""
    async def _run():
        delays = {"a": 0.12, "b": 0.02, "c": 0.06}
        calls = [{"id": k} for k in delays]

        async def executor_fn(call):
            tid = call["id"]
            await asyncio.sleep(delays[tid])
            return ToolResult(tool_id=tid, success=True, data=tid)

        executor = StreamingToolExecutor(max_concurrent=3)
        results = []
        async for r in executor.execute_streaming(calls, executor_fn):
            results.append(r.tool_id)
        return results

    order = run(_run())
    # b (0.02) < c (0.06) < a (0.12)
    assert order == ["b", "c", "a"]


def test_streaming_executor_concurrency_limit():
    """Semaphore should limit concurrent executions."""
    concurrent = {"count": 0, "max": 0}

    async def _run():
        calls = [{"id": str(i)} for i in range(10)]

        async def executor_fn(call):
            concurrent["count"] += 1
            if concurrent["count"] > concurrent["max"]:
                concurrent["max"] = concurrent["count"]
            await asyncio.sleep(0.05)
            concurrent["count"] -= 1
            return ToolResult(tool_id=call["id"], success=True)

        executor = StreamingToolExecutor(max_concurrent=2)
        results = []
        async for r in executor.execute_streaming(calls, executor_fn):
            results.append(r)
        return results

    results = run(_run())
    assert len(results) == 10
    assert concurrent["max"] <= 2


def test_streaming_executor_non_fatal_error():
    """Non-fatal exceptions become failed ToolResults."""
    async def _run():
        calls = [{"id": "ok"}, {"id": "fail"}, {"id": "ok2"}]

        async def executor_fn(call):
            if call["id"] == "fail":
                raise ValueError("boom")
            return ToolResult(tool_id=call["id"], success=True)

        executor = StreamingToolExecutor(max_concurrent=3)
        results = []
        async for r in executor.execute_streaming(calls, executor_fn):
            results.append(r)
        return results

    results = run(_run())
    by_id = {r.tool_id: r for r in results}
    assert by_id["ok"].success is True
    assert by_id["fail"].success is False
    assert "boom" in by_id["fail"].error
    assert by_id["ok2"].success is True


def test_streaming_executor_fatal_cancel():
    """Fatal exception cancels remaining tasks and re-raises."""
    async def _run():
        calls = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

        async def executor_fn(call):
            if call["id"] == "a":
                raise SystemExit("fatal")
            await asyncio.sleep(1)
            return ToolResult(tool_id=call["id"], success=True)

        executor = StreamingToolExecutor(max_concurrent=3)
        results = []
        try:
            async for r in executor.execute_streaming(calls, executor_fn):
                results.append(r)
        except SystemExit:
            return "caught"
        return results

    assert run(_run()) == "caught"


# ── ContextWindow ────────────────────────────────────────────────────────

def test_context_window_add_and_get():
    cw = ContextWindow(max_tokens=1000)
    cw.add("hello", "user")
    cw.add("hi there", "assistant")
    msgs = cw.get_messages()
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": "hello"}
    assert msgs[1] == {"role": "assistant", "content": "hi there"}


def test_context_window_token_estimation():
    cw = ContextWindow(max_tokens=100)
    # ~4 chars per token, so 40 chars ≈ 10 tokens + 1 = 11
    cw.add("a" * 40, "user")
    assert cw.current_tokens == 11


def test_context_window_pressure():
    cw = ContextWindow(max_tokens=100)
    cw.add("x" * 396, "user")  # 396//4 + 1 = 100 tokens
    assert cw.pressure == 1.0

    cw2 = ContextWindow(max_tokens=1000)
    cw2.add("x" * 40, "user")  # 11 tokens
    assert 0.0 < cw2.pressure < 0.2


def test_context_window_auto_compact_naive():
    async def _run():
        cw = ContextWindow(max_tokens=1000)
        cw.add("system prompt", "system")
        for i in range(20):
            cw.add(f"message {i}", "user" if i % 2 == 0 else "assistant")

        # Force high pressure by setting a tiny window
        cw._max_tokens = cw.current_tokens  # pressure ≈ 1.0
        await cw.auto_compact(threshold=0.5)
        msgs = cw.get_messages()
        return msgs

    msgs = run(_run())
    # Should have kept system + last half
    assert msgs[0]["role"] == "system"
    assert len(msgs) < 21  # compacted


def test_context_window_auto_compact_custom_compressor():
    async def my_compressor(messages):
        return [{"role": "system", "content": "compressed"}]

    async def _run():
        cw = ContextWindow(max_tokens=1)
        cw.add("a" * 1000, "user")
        await cw.auto_compact(threshold=0.01, compressor=my_compressor)
        return cw.get_messages()

    msgs = run(_run())
    assert msgs == [{"role": "system", "content": "compressed"}]


# ── BackPressureController ───────────────────────────────────────────────

def test_backpressure_init_validation():
    try:
        BackPressureController(high_water=0.3, low_water=0.7)
        assert False, "Should have raised"
    except ValueError:
        pass


def test_backpressure_pause_resume():
    bp = BackPressureController(high_water=0.8, low_water=0.6)

    # Low pressure — no pause
    bp.update(100, 1000)
    assert bp.should_pause() is False
    assert bp.should_resume() is True

    # Cross high water — pause
    bp.update(850, 1000)
    assert bp.should_pause() is True

    # Drop below low water — resume
    bp.update(500, 1000)
    assert bp.should_pause() is False


def test_backpressure_hysteresis():
    """Between low and high water the state should not flip."""
    bp = BackPressureController(high_water=0.8, low_water=0.6)

    # Go above high water
    bp.update(900, 1000)
    assert bp.should_pause() is True

    # Drop to 0.7 (between low and high) — should STAY paused
    bp.update(700, 1000)
    assert bp.should_pause() is True

    # Drop below low water
    bp.update(500, 1000)
    assert bp.should_pause() is False


def test_backpressure_edge_zero_max():
    bp = BackPressureController()
    bp.update(0, 0)
    assert bp.pressure == 1.0
    assert bp.should_pause() is True


# ── integration ──────────────────────────────────────────────────────────

def test_pipeline_with_context_window():
    """Pipeline that processes messages and adds them to context."""
    async def _run():
        cw = ContextWindow(max_tokens=10000)

        p = Pipeline().map("prefix", lambda m: f"[processed] {m}")

        messages = ["hello", "world"]
        results = []
        for msg in messages:
            async for r in p.execute(msg):
                cw.add(r, "user")
                results.append(r)

        return cw.get_messages(), results

    msgs, results = run(_run())
    assert results == ["[processed] hello", "[processed] world"]
    assert len(msgs) == 2


# ── run all ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Discover and run all test_* functions
    import inspect
    passed = failed = 0
    for name, fn in sorted(inspect.getmembers(sys.modules[__name__], inspect.isfunction)):
        if name.startswith("test_"):
            try:
                fn()
                passed += 1
                print(f"  ✓ {name}")
            except Exception as e:
                failed += 1
                print(f"  ✗ {name}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
