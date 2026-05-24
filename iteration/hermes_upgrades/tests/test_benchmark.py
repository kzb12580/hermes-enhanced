"""Benchmark tests for Hermes Agent V2 modules.

Run with: python -m pytest tests/test_benchmark.py -v -s
"""

import time
import random
import string
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_text(n_chars: int) -> str:
    """Generate random printable text of approximately *n_chars* characters."""
    return "".join(random.choices(string.ascii_letters + string.digits + " \n", k=n_chars))


def _timing(label: str, fn, results: list) -> None:
    """Run *fn*, record (label, elapsed_ms) in *results*, assert no error."""
    t0 = time.perf_counter()
    fn()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    results.append((label, elapsed_ms))


# ---------------------------------------------------------------------------
# 1. Orchestrator: partition 100 mixed tool calls
# ---------------------------------------------------------------------------

def test_bench_orchestrator_partition():
    """Partition 100 mixed tool calls, measure ms."""
    from tool_orchestrator import ToolCall, ToolOrchestrator, ConcurrencyClass

    orch = ToolOrchestrator()

    tool_names = ["read_file", "search_files", "terminal", "write_file",
                  "web_search", "patch", "session_search", "send_message"]
    calls = [
        ToolCall(name=random.choice(tool_names), args={"path": f"/tmp/file{i}.txt"})
        for i in range(100)
    ]

    results = []

    def run():
        batches = orch.partition(calls)
        return batches

    _timing("Orchestrator partition (100 calls)", run, results)
    label, ms = results[0]
    print(f"\n  {label}: {ms:.2f} ms")
    assert ms >= 0


# ---------------------------------------------------------------------------
# 2. Orchestrator: concurrent vs sequential 100 reads
# ---------------------------------------------------------------------------

def test_bench_orchestrator_concurrent_vs_sequential():
    """Execute 100 reads concurrently vs sequentially, compare."""
    from tool_orchestrator import ToolCall, ToolOrchestrator

    calls = [ToolCall(name="read_file", args={"path": f"/tmp/f{i}"}) for i in range(100)]

    def fake_executor(tc):
        # Simulate a small I/O delay
        time.sleep(0.001)
        return f"content of {tc.args['path']}"

    # Sequential
    orch_seq = ToolOrchestrator(max_workers=1)
    t0 = time.perf_counter()
    batches_seq = orch_seq.partition(calls)
    seq_results = orch_seq.execute(batches_seq, fake_executor)
    seq_ms = (time.perf_counter() - t0) * 1000

    # Concurrent
    orch_con = ToolOrchestrator(max_workers=16)
    t0 = time.perf_counter()
    batches_con = orch_con.partition(calls)
    con_results = orch_con.execute(batches_con, fake_executor)
    con_ms = (time.perf_counter() - t0) * 1000

    speedup = seq_ms / con_ms if con_ms > 0 else float("inf")
    print(f"\n  Sequential (100 reads): {seq_ms:.2f} ms")
    print(f"  Concurrent (100 reads): {con_ms:.2f} ms")
    print(f"  Speedup: {speedup:.2f}x")

    assert len(seq_results) == 100
    assert len(con_results) == 100
    # Concurrent should be meaningfully faster given the 1ms sleep per call
    assert speedup > 2.0, f"Expected speedup > 2x, got {speedup:.2f}x"


# ---------------------------------------------------------------------------
# 3. Result Manager: process 500 results, dedup hit rate
# ---------------------------------------------------------------------------

def test_bench_result_manager_dedup():
    """Process 500 results, measure dedup hit rate."""
    from tool_result_manager import ToolResultManager

    mgr = ToolResultManager(max_tokens=100_000)
    results = []

    # 250 unique, each repeated once → 500 total, expect ~50% dedup
    unique_texts = [_random_text(500) for _ in range(250)]
    all_texts = unique_texts + unique_texts  # 500
    random.shuffle(all_texts)

    def run():
        for txt in all_texts:
            mgr.process("read_file", txt)

    _timing("Result Manager: process 500 results", run, results)
    label, ms = results[0]
    stats = mgr.get_stats()
    dedup_rate = stats["dedup_saves"] / stats["total_processed"] * 100

    print(f"\n  {label}: {ms:.2f} ms")
    print(f"  Dedup hits: {stats['dedup_saves']}/{stats['total_processed']} ({dedup_rate:.1f}%)")

    assert stats["total_processed"] == 500
    assert stats["dedup_saves"] == 250, f"Expected 250 dedup saves, got {stats['dedup_saves']}"


# ---------------------------------------------------------------------------
# 4. Result Manager: truncate 100 x 50KB results
# ---------------------------------------------------------------------------

def test_bench_result_manager_truncation():
    """Truncate 100 × 50KB results, measure ms."""
    from tool_result_manager import ToolResultManager

    mgr = ToolResultManager(max_tokens=80_000)
    texts = [_random_text(50_000) for _ in range(100)]
    results = []

    def run():
        for txt in texts:
            mgr.process("terminal", txt)

    _timing("Result Manager: truncate 100x50KB", run, results)
    label, ms = results[0]
    stats = mgr.get_stats()

    print(f"\n  {label}: {ms:.2f} ms")
    print(f"  Truncations: {stats['truncations']}")

    assert stats["truncations"] > 0


# ---------------------------------------------------------------------------
# 5. Compressor: microcompact on 50-turn conversation
# ---------------------------------------------------------------------------

def _make_conversation(n_turns: int) -> list[dict]:
    """Create a synthetic conversation with *n_turns* tool-result-heavy messages."""
    msgs: list[dict] = [{"role": "system", "content": "You are a helpful assistant."}]
    for i in range(n_turns):
        msgs.append({"role": "user", "content": f"Question {i}: {_random_text(200)}"})
        msgs.append({"role": "assistant", "content": f"Let me look that up for you. Turn {i}."})
        msgs.append({"role": "tool", "name": "read_file", "content": _random_text(5000)})
        msgs.append({"role": "assistant", "content": f"Here is the answer for turn {i}. {_random_text(300)}"})
    return msgs


def test_bench_compressor_microcompact():
    """Microcompact on 50-turn conversation, measure ms."""
    from context_compressor_v2 import ContextCompressorV2

    compressor = ContextCompressorV2(model_token_limit=200_000, profile="balanced")
    msgs = _make_conversation(50)
    results = []

    def run():
        return compressor.compress(msgs, level="micro")

    _timing("Compressor: microcompact (50 turns)", run, results)
    label, ms = results[0]
    print(f"\n  {label}: {ms:.2f} ms")
    assert ms >= 0


# ---------------------------------------------------------------------------
# 6. Compressor: reactive compress on 50-turn conversation
# ---------------------------------------------------------------------------

def test_bench_compressor_reactive():
    """Reactive compress on 50-turn conversation, measure ms."""
    from context_compressor_v2 import ContextCompressorV2

    compressor = ContextCompressorV2(model_token_limit=200_000, profile="balanced")
    msgs = _make_conversation(50)
    results = []

    def run():
        return compressor.compress(msgs, level="reactive")

    _timing("Compressor: reactive (50 turns)", run, results)
    label, ms = results[0]
    print(f"\n  {label}: {ms:.2f} ms")
    assert ms >= 0


# ---------------------------------------------------------------------------
# 7. Permission: check 1000 calls against default rules
# ---------------------------------------------------------------------------

def test_bench_permission_check():
    """Check 1000 calls against default rules, measure ms."""
    from permission_pipeline import PermissionPipeline

    pipeline = PermissionPipeline()  # default rules
    tool_names = ["read_file", "write_file", "terminal", "search_files",
                  "web_search", "patch", "send_message", "unknown_tool"]
    checks = [(random.choice(tool_names), {"command": "ls", "path": "/tmp"}) for _ in range(1000)]
    results = []

    def run():
        for tn, args in checks:
            pipeline.check(tn, args)

    _timing("Permission: check 1000 calls", run, results)
    label, ms = results[0]
    print(f"\n  {label}: {ms:.2f} ms")
    assert ms >= 0


# ---------------------------------------------------------------------------
# 8. Memory: add 200 + search 100
# ---------------------------------------------------------------------------

def test_bench_memory_add_and_search():
    """Add 200 memories + search 100 queries, measure ms."""
    from memory_system import MemoryStore, MemoryEntry, MemoryType

    store = MemoryStore(max_entries=500)
    results = []

    entries = [
        MemoryEntry(
            type=random.choice(list(MemoryType)),
            content=_random_text(300),
            tags=[f"tag{i % 10}", f"cat{i % 5}"],
        )
        for i in range(200)
    ]
    queries = [_random_text(20) for _ in range(100)]

    def run_add():
        for e in entries:
            store.add(e)

    def run_search():
        for q in queries:
            store.search(q, limit=5)

    _timing("Memory: add 200 entries", run_add, results)
    _timing("Memory: search 100 queries", run_search, results)

    for label, ms in results:
        print(f"\n  {label}: {ms:.2f} ms")

    assert len(store.entries) == 200


# ---------------------------------------------------------------------------
# 9. Coordinator: full cycle 10 tasks
# ---------------------------------------------------------------------------

def test_bench_coordinator_full_cycle():
    """Full cycle (plan→assign→execute→review→aggregate) for 10 tasks, measure ms."""
    from coordinator import (
        Coordinator, TaskSpec, AgentProfile, AgentRole,
    )

    objective = (
        "Implement the new API endpoint. "
        "Write unit tests for the API. "
        "Research best practices for authentication. "
        "Deploy to staging environment. "
        "Review the pull request. "
        "Design the database schema. "
        "Run integration tests. "
        "Fix the critical bug in login. "
        "Document the API endpoints. "
        "Analyze the performance metrics."
    )

    def executor(task: TaskSpec) -> dict:
        return {"status": "ok", "output": f"Completed: {task.description[:40]}"}

    def reviewer(task: TaskSpec) -> dict:
        return {"approved": True, "score": random.randint(7, 10)}

    results = []

    def make_coord():
        return Coordinator(agents=[
            AgentProfile(
                role=AgentRole.ORCHESTRATOR,
                name="orchestrator",
                capabilities=["code", "research", "design", "review", "deploy", "test", "data"],
            ),
            AgentProfile(
                role=AgentRole.WORKER,
                name="worker-1",
                capabilities=["code", "research", "design", "deploy", "test", "data"],
                max_tasks=10,
            ),
            AgentProfile(
                role=AgentRole.WORKER,
                name="worker-2",
                capabilities=["code", "research", "design", "deploy", "test", "data"],
                max_tasks=10,
            ),
        ])

    def run():
        c = make_coord()
        return c.run_full_cycle(objective, executor, reviewer)

    _timing("Coordinator: full cycle (10 tasks)", run, results)
    label, ms = results[0]
    agg = run()  # re-run to inspect
    print(f"\n  {label}: {ms:.2f} ms")
    print(f"  Result: {agg.summary}")

    assert len(agg.failed_tasks) == 0, f"Failed tasks: {agg.failed_tasks}"
    assert sum(1 for d in agg.details if d["status"] == "completed") >= 9


# ---------------------------------------------------------------------------
# Summary printer — runs after all benchmarks
# ---------------------------------------------------------------------------

# This runs automatically because pytest collects test functions above.
# Each prints its own timing. We add a final table summary via a session-scoped fixture.

_COLLECTED: list[tuple[str, float]] = []


def test_bench_summary():
    """Print a summary table of all benchmark timings."""
    # We rely on the stdout from each test; this is just a separator.
    print("\n" + "=" * 60)
    print("  BENCHMARK SUMMARY — see individual test output above")
    print("=" * 60)
    assert True
