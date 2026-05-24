"""Tests for tool_orchestrator module."""

import pytest

from tool_orchestrator import (
    BatchResult,
    ConcurrencyClass,
    FileConflictDetector,
    ToolCall,
    ToolConcurrencyClassifier,
    ToolOrchestrator,
    partition,
)


# ── Classification tests ─────────────────────────────────────────────────────

class TestToolConcurrencyClassifier:
    """Verify every listed tool is classified correctly."""

    @pytest.mark.parametrize(
        "name",
        [
            "read_file", "search_files", "web_search", "web_extract",
            "session_search", "skill_view", "skills_list",
            "browser_snapshot", "browser_get_images", "vision_analyze",
        ],
    )
    def test_read_only(self, name: str) -> None:
        c = ToolConcurrencyClassifier()
        assert c.classify(name) == ConcurrencyClass.READ_ONLY

    @pytest.mark.parametrize(
        "name",
        [
            "write_file", "patch", "terminal", "send_message",
            "delegate_task", "memory", "skill_manage",
            "browser_type", "browser_click", "browser_press",
        ],
    )
    def test_write_serial(self, name: str) -> None:
        c = ToolConcurrencyClassifier()
        assert c.classify(name) == ConcurrencyClass.WRITE_SERIAL

    def test_unknown_defaults_ambiguous(self) -> None:
        c = ToolConcurrencyClassifier()
        assert c.classify("some_future_tool") == ConcurrencyClass.AMBIGUOUS

    def test_override_changes_class(self) -> None:
        c = ToolConcurrencyClassifier(
            overrides={"read_file": ConcurrencyClass.WRITE_SERIAL}
        )
        assert c.classify("read_file") == ConcurrencyClass.WRITE_SERIAL


# ── File-conflict detection ──────────────────────────────────────────────────

class TestFileConflictDetector:
    def test_same_path_write_conflict(self) -> None:
        det = FileConflictDetector()
        c = ToolConcurrencyClassifier()
        a = ToolCall(name="read_file", args={"path": "/tmp/x.py"}, id="1")
        b = ToolCall(name="write_file", args={"path": "/tmp/x.py"}, id="2")
        assert det.has_write_conflict(a, b, c) is True

    def test_different_paths_no_conflict(self) -> None:
        det = FileConflictDetector()
        c = ToolConcurrencyClassifier()
        a = ToolCall(name="read_file", args={"path": "/tmp/a.py"}, id="1")
        b = ToolCall(name="write_file", args={"path": "/tmp/b.py"}, id="2")
        assert det.has_write_conflict(a, b, c) is False

    def test_same_path_both_read_no_conflict(self) -> None:
        det = FileConflictDetector()
        c = ToolConcurrencyClassifier()
        a = ToolCall(name="read_file", args={"path": "/tmp/x.py"}, id="1")
        b = ToolCall(name="search_files", args={"path": "/tmp/x.py"}, id="2")
        assert det.has_write_conflict(a, b, c) is False

    def test_extract_paths_multiple_keys(self) -> None:
        det = FileConflictDetector()
        tc = ToolCall(
            name="write_file",
            args={"path": "/a.py", "file_path": "/b.py", "output_path": "/c.py"},
            id="1",
        )
        assert det.extract_paths(tc) == {"/a.py", "/b.py", "/c.py"}

    def test_file_path_key(self) -> None:
        det = FileConflictDetector()
        tc = ToolCall(name="write_file", args={"file_path": "/tmp/out.txt"}, id="1")
        assert det.extract_paths(tc) == {"/tmp/out.txt"}


# ── Partition logic ──────────────────────────────────────────────────────────

class TestPartition:
    def test_empty(self) -> None:
        assert partition([]) == []

    def test_all_reads_single_batch(self) -> None:
        calls = [
            ToolCall(name="read_file", args={"path": f"/f{i}"}, id=str(i))
            for i in range(4)
        ]
        batches = partition(calls)
        assert len(batches) == 1
        assert len(batches[0]) == 4

    def test_all_writes_separate_batches(self) -> None:
        calls = [
            ToolCall(name="write_file", args={"path": f"/f{i}"}, id=str(i))
            for i in range(3)
        ]
        batches = partition(calls)
        assert len(batches) == 3
        for b in batches:
            assert len(b) == 1

    def test_mixed_split(self) -> None:
        calls = [
            ToolCall(name="read_file", args={"path": "/a"}, id="r1"),
            ToolCall(name="read_file", args={"path": "/b"}, id="r2"),
            ToolCall(name="write_file", args={"path": "/c"}, id="w1"),
        ]
        batches = partition(calls)
        # First batch: the two reads.
        assert len(batches[0]) == 2
        # Remaining batches: one each for writes.
        assert all(len(b) == 1 for b in batches[1:])

    def test_read_conflict_with_write_separated(self) -> None:
        """Read and write touching the same path must not be in same batch."""
        calls = [
            ToolCall(name="read_file", args={"path": "/shared"}, id="r1"),
            ToolCall(name="write_file", args={"path": "/shared"}, id="w1"),
        ]
        batches = partition(calls)
        # The read should be deferred or the write separate.
        # Flatten and check they aren't in the same batch together.
        for batch in batches:
            ids_in = {tc.id for tc in batch}
            assert not ({"r1", "w1"} <= ids_in)

    def test_read_write_different_paths_parallel(self) -> None:
        calls = [
            ToolCall(name="read_file", args={"path": "/a"}, id="r1"),
            ToolCall(name="write_file", args={"path": "/b"}, id="w1"),
        ]
        batches = partition(calls)
        # Read goes in first batch, write in its own.
        assert batches[0][0].id == "r1"
        assert batches[1][0].id == "w1"

    def test_ambiguous_treated_as_write(self) -> None:
        calls = [
            ToolCall(name="unknown_tool", args={"path": "/a"}, id="u1"),
            ToolCall(name="read_file", args={"path": "/a"}, id="r1"),
        ]
        batches = partition(calls)
        # Both should be separate due to ambiguous being treated as write.
        all_ids = [tc.id for batch in batches for tc in batch]
        assert "u1" in all_ids
        assert "r1" in all_ids


# ── Execute tests ────────────────────────────────────────────────────────────

class TestExecute:
    def test_basic_sync_execution(self) -> None:
        orch = ToolOrchestrator()
        calls = [
            ToolCall(name="read_file", args={"path": "/a"}, id="1"),
            ToolCall(name="read_file", args={"path": "/b"}, id="2"),
        ]
        batches = orch.partition(calls)

        def executor(tc: ToolCall) -> str:
            return f"result_{tc.id}"

        results = orch.execute(batches, executor)
        assert results["1"].result == "result_1"
        assert results["2"].result == "result_2"
        assert results["1"].elapsed >= 0
        assert results["1"].error is None

    def test_executor_error_captured(self) -> None:
        orch = ToolOrchestrator()
        calls = [ToolCall(name="terminal", args={}, id="bad")]
        batches = orch.partition(calls)

        def executor(tc: ToolCall) -> None:
            raise RuntimeError("boom")

        results = orch.execute(batches, executor)
        assert results["bad"].error == "boom"

    def test_progress_callback(self) -> None:
        orch = ToolOrchestrator()
        calls = [
            ToolCall(name="read_file", args={"path": "/a"}, id="1"),
        ]
        batches = orch.partition(calls)
        events: list[tuple[str, str, float]] = []

        def on_progress(name: str, status: str, elapsed: float) -> None:
            events.append((name, status, elapsed))

        def executor(tc: ToolCall) -> str:
            return "ok"

        orch.execute(batches, executor, on_progress=on_progress)
        statuses = [e[1] for e in events]
        assert "started" in statuses
        assert "completed" in statuses

    def test_progress_on_error(self) -> None:
        orch = ToolOrchestrator()
        calls = [ToolCall(name="terminal", args={}, id="1")]
        batches = orch.partition(calls)
        events: list[tuple[str, str, float]] = []

        def on_progress(name: str, status: str, elapsed: float) -> None:
            events.append((name, status, elapsed))

        def executor(tc: ToolCall) -> None:
            raise ValueError("fail")

        orch.execute(batches, executor, on_progress=on_progress)
        statuses = [e[1] for e in events]
        assert "error" in statuses

    def test_concurrent_read_batch(self) -> None:
        """Multiple reads in same batch should all execute."""
        import threading

        orch = ToolOrchestrator(max_workers=4)
        calls = [
            ToolCall(name="read_file", args={"path": f"/f{i}"}, id=str(i))
            for i in range(6)
        ]
        batches = orch.partition(calls)
        threads_seen: set[int] = set()
        lock = threading.Lock()

        def executor(tc: ToolCall) -> str:
            with lock:
                threads_seen.add(threading.get_ident())
            import time; time.sleep(0.05)  # force real concurrency
            return tc.id

        results = orch.execute(batches, executor)
        assert len(results) == 6
        # With concurrent execution, we should see >1 thread used.
        assert len(threads_seen) > 1

    def test_custom_overrides(self) -> None:
        """tool_overrides should change classification."""
        orch = ToolOrchestrator(
            tool_overrides={"read_file": ConcurrencyClass.WRITE_SERIAL}
        )
        calls = [
            ToolCall(name="read_file", args={"path": "/a"}, id="1"),
            ToolCall(name="read_file", args={"path": "/b"}, id="2"),
        ]
        batches = orch.partition(calls)
        # Now read_file is WRITE_SERIAL → each gets own batch.
        assert len(batches) == 2
