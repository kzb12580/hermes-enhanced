"""Algorithm correctness tests for hermes_upgrades.

Covers all 8 algorithmic review areas:
1. Token estimation accuracy
2. TF-IDF implementation
3. Content similarity
4. Circuit breaker timing
5. Exponential backoff jitter
6. LRU eviction
7. Back-pressure hysteresis
8. Task scheduling
"""

import math
import threading
import time
from collections import OrderedDict, Counter

import pytest


# ---------------------------------------------------------------------------
# 1. Token Estimation
# ---------------------------------------------------------------------------


class TestTokenEstimation:
    """Verify the 4-chars/token heuristic and consistency across modules."""

    def test_english_prose_reasonable(self):
        from token_utils import estimate_tokens
        # English averages ~4 chars/token
        text = "The quick brown fox jumps over the lazy dog"  # 43 chars
        tokens = estimate_tokens(text)
        # Expected ~10-11 tokens; estimator gives 43//4 = 10
        assert 8 <= tokens <= 13, f"Got {tokens}, expected ~10"

    def test_chinese_underestimate(self):
        from token_utils import estimate_tokens
        # Chinese: each char ≈ 1-2 tokens, so 4 chars/token is a bad fit
        text = "你好世界欢迎使用这个系统"  # 10 chars
        tokens = estimate_tokens(text)
        # Actual would be ~10-20 tokens; estimator gives 10//4 = 2
        # This documents the known underestimate
        assert tokens <= 5, f"Estimator gives {tokens}, actual would be ~10-20"

    def test_code_slight_overestimate(self):
        from token_utils import estimate_tokens
        code = "def foo(x):\n    return x + 1\n"  # 28 chars
        tokens = estimate_tokens(code)
        # Code averages ~3.2 chars/token → ~8-9 tokens; estimator gives 28//4 = 7
        assert 5 <= tokens <= 10

    def test_empty_returns_zero(self):
        from token_utils import estimate_tokens
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_minimum_one_token(self):
        from token_utils import estimate_tokens
        assert estimate_tokens("x") == 1  # max(1, 1//4) = 1

    def test_multipart_content(self):
        from token_utils import estimate_content_tokens
        content = [
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ]
        tokens = estimate_content_tokens(content)
        assert tokens > 0

    def test_consistency_token_utils_vs_tool_result_manager(self):
        """token_utils and TokenEstimator should give same results."""
        from token_utils import estimate_tokens
        from tool_result_manager import TokenEstimator
        text = "Hello, this is a test string for consistency"
        assert estimate_tokens(text) == TokenEstimator.estimate_tokens(text)

    def test_consistency_token_utils_vs_context_compressor(self):
        """token_utils and context_compressor_v2._estimate_tokens should match."""
        from token_utils import estimate_tokens
        from context_compressor_v2 import _estimate_tokens
        text = "Another test string for cross-module consistency"
        assert estimate_tokens(text) == _estimate_tokens(text)


# ---------------------------------------------------------------------------
# 2. TF-IDF
# ---------------------------------------------------------------------------


class TestTFIDF:
    """Verify TF-IDF normalization and correctness."""

    def test_tf_normalized_sum_to_one(self):
        from memory_system import _tf
        tokens = ["cat", "dog", "cat", "bird"]
        tf = _tf(tokens)
        assert abs(sum(tf.values()) - 1.0) < 1e-9, f"TF sums to {sum(tf.values())}"
        assert abs(tf["cat"] - 0.5) < 1e-9
        assert abs(tf["dog"] - 0.25) < 1e-9
        assert abs(tf["bird"] - 0.25) < 1e-9

    def test_tf_empty_tokens(self):
        from memory_system import _tf
        tf = _tf([])
        assert tf == {}

    def test_tf_document_length_invariant(self):
        """Two docs with same term proportion should have same TF for that term."""
        from memory_system import _tf
        short = ["python", "code"]
        long = ["python", "code"] * 100
        tf_short = _tf(short)
        tf_long = _tf(long)
        assert abs(tf_short["python"] - tf_long["python"]) < 1e-9

    def test_idf_rare_terms_score_higher(self):
        from memory_system import _idf
        docs = [
            ["common", "word"],
            ["common", "rare"],
            ["common", "other"],
        ]
        idf = _idf(docs)
        # "common" appears in 3/3 docs → low IDF
        # "rare" appears in 1/3 docs → high IDF
        assert idf["rare"] > idf["common"]

    def test_idf_single_doc(self):
        from memory_system import _idf
        docs = [["hello", "world"]]
        idf = _idf(docs)
        assert idf["hello"] > 0
        assert idf["world"] > 0

    def test_search_score_longer_doc_not_biased(self):
        """After normalization fix, a longer doc shouldn't score disproportionately higher."""
        from memory_system import MemorySearch, MemoryEntry, MemoryType, _idf, _tokenize
        from datetime import datetime, timezone

        search = MemorySearch()
        idf_map = {"test": 1.5}

        short_entry = MemoryEntry(
            type=MemoryType.MEMORY,
            content="test",
            created_at=datetime.now(timezone.utc),
        )
        long_entry = MemoryEntry(
            type=MemoryType.MEMORY,
            content="test " * 100,  # "test" appears 100 times
            created_at=datetime.now(timezone.utc),
        )

        score_short = search.score("test", short_entry, idf_map, max_access=1)
        score_long = search.score("test", long_entry, idf_map, max_access=1)

        # With normalized TF, long entry should NOT be 100× higher
        # The ratio should be close to 1.0 (same term proportion)
        ratio = score_long / score_short if score_short > 0 else float("inf")
        assert ratio < 3.0, f"Long doc scores {ratio}x higher than short doc"


# ---------------------------------------------------------------------------
# 3. Content Similarity
# ---------------------------------------------------------------------------


class TestContentSimilarity:
    """Verify SequenceMatcher-based similarity."""

    def test_identical_strings(self):
        from auto_dream import MemoryConsolidator
        assert MemoryConsolidator.content_similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        from auto_dream import MemoryConsolidator
        sim = MemoryConsolidator.content_similarity("abc", "xyz")
        assert sim < 0.5

    def test_case_insensitive(self):
        from auto_dream import MemoryConsolidator
        assert MemoryConsolidator.content_similarity("Hello", "hello") == 1.0

    def test_partial_overlap(self):
        from auto_dream import MemoryConsolidator
        sim = MemoryConsolidator.content_similarity(
            "python is great",
            "python is awesome",
        )
        assert 0.5 < sim < 1.0

    def test_empty_strings(self):
        from auto_dream import MemoryConsolidator
        assert MemoryConsolidator.content_similarity("", "") == 1.0

    def test_threshold_applied_correctly(self):
        from auto_dream import MemoryConsolidator
        # Threshold is 0.6
        # These should be similar enough
        sim = MemoryConsolidator.content_similarity(
            "I prefer dark mode for all applications",
            "I prefer dark mode for all my applications",
        )
        assert sim >= 0.6


# ---------------------------------------------------------------------------
# 4. Circuit Breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Verify circuit breaker state machine correctness."""

    def test_closed_allows_requests(self):
        from smart_retry import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        from smart_retry import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self):
        from smart_retry import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state.value == "open"
        time.sleep(0.02)
        assert cb.allow_request() is True
        assert cb.state.value == "half_open"

    def test_half_open_allows_only_one_probe(self):
        """Bug #1 fix: only one request should pass through in HALF_OPEN."""
        from smart_retry import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        # First request transitions to HALF_OPEN
        assert cb.allow_request() is True
        # Second request should be blocked
        assert cb.allow_request() is False

    def test_failed_probe_reopens_circuit(self):
        """Bug #2 fix: failed probe should immediately reopen circuit."""
        from smart_retry import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        # Transition to HALF_OPEN
        cb.allow_request()
        # Probe fails
        cb.record_failure()
        assert cb.state.value == "open"
        # Should be blocked again
        assert cb.allow_request() is False

    def test_successful_probe_closes_circuit(self):
        from smart_retry import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()
        cb.record_success()
        assert cb.state.value == "closed"
        assert cb.allow_request() is True

    def test_reset_clears_probe_state(self):
        from smart_retry import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()
        cb.reset()
        assert cb.state.value == "closed"
        assert cb.allow_request() is True


# ---------------------------------------------------------------------------
# 5. Exponential Backoff Jitter
# ---------------------------------------------------------------------------


class TestBackoffJitter:
    """Verify exponential backoff delay calculation."""

    def test_base_delay_correct(self):
        from smart_retry import SmartRetryManager, RetryPolicy
        mgr = SmartRetryManager()
        policy = RetryPolicy(base_delay=1.0, backoff_factor=2.0, jitter=0.0)
        # With zero jitter, delay should be exact
        delay = mgr._calculate_delay(policy, 0)
        assert abs(delay - 1.0) < 0.01

    def test_exponential_growth(self):
        from smart_retry import SmartRetryManager, RetryPolicy
        mgr = SmartRetryManager()
        policy = RetryPolicy(base_delay=1.0, backoff_factor=2.0, jitter=0.0)
        delays = [mgr._calculate_delay(policy, i) for i in range(4)]
        assert abs(delays[0] - 1.0) < 0.01
        assert abs(delays[1] - 2.0) < 0.01
        assert abs(delays[2] - 4.0) < 0.01
        assert abs(delays[3] - 8.0) < 0.01

    def test_max_delay_cap(self):
        from smart_retry import SmartRetryManager, RetryPolicy
        mgr = SmartRetryManager()
        policy = RetryPolicy(base_delay=1.0, backoff_factor=2.0, max_delay=5.0, jitter=0.0)
        delay = mgr._calculate_delay(policy, 10)  # would be 1024 without cap
        assert delay <= 5.0

    def test_jitter_adds_variance(self):
        from smart_retry import SmartRetryManager, RetryPolicy
        mgr = SmartRetryManager()
        policy = RetryPolicy(base_delay=4.0, backoff_factor=1.0, jitter=0.25)
        delays = [mgr._calculate_delay(policy, 0) for _ in range(100)]
        # With jitter=0.25, range should be [3.0, 5.0]
        assert all(3.0 <= d <= 5.0 for d in delays)
        # Should have variance
        assert len(set(round(d, 1) for d in delays)) > 5

    def test_minimum_delay(self):
        from smart_retry import SmartRetryManager, RetryPolicy
        mgr = SmartRetryManager()
        policy = RetryPolicy(base_delay=0.001, backoff_factor=0.001, jitter=0.99)
        delay = mgr._calculate_delay(policy, 0)
        assert delay >= 0.05  # minimum 50ms


# ---------------------------------------------------------------------------
# 6. LRU Eviction
# ---------------------------------------------------------------------------


class TestLRUEviction:
    """Verify LRU deduplication in ResultDeduplicator."""

    def test_basic_lru_order(self):
        from tool_result_manager import ResultDeduplicator
        dedup = ResultDeduplicator(max_seen=3)
        dedup.register("a")
        dedup.register("b")
        dedup.register("c")
        # All should be seen
        assert dedup.is_duplicate("a")
        assert dedup.is_duplicate("b")
        assert dedup.is_duplicate("c")

    def test_eviction_of_oldest(self):
        from tool_result_manager import ResultDeduplicator
        dedup = ResultDeduplicator(max_seen=3)
        dedup.register("a")
        dedup.register("b")
        dedup.register("c")
        # "a" is LRU → should be evicted
        dedup.register("d")
        assert not dedup.is_duplicate("a")
        assert dedup.is_duplicate("b")

    def test_access_promotes_to_mru(self):
        from tool_result_manager import ResultDeduplicator
        dedup = ResultDeduplicator(max_seen=3)
        dedup.register("a")
        dedup.register("b")
        dedup.register("c")
        # Access "a" → promotes to MRU
        dedup.is_duplicate("a")
        # Now "b" is LRU → should be evicted
        dedup.register("d")
        assert dedup.is_duplicate("a")  # still present
        assert not dedup.is_duplicate("b")  # evicted

    def test_max_seen_respected(self):
        from tool_result_manager import ResultDeduplicator
        dedup = ResultDeduplicator(max_seen=5)
        for i in range(10):
            dedup.register(str(i))
        # Only last 5 should be present
        assert not dedup.is_duplicate("0")
        assert not dedup.is_duplicate("4")
        assert dedup.is_duplicate("5")
        assert dedup.is_duplicate("9")

    def test_clear_resets_state(self):
        from tool_result_manager import ResultDeduplicator
        dedup = ResultDeduplicator(max_seen=5)
        dedup.register("test")
        dedup.clear()
        assert not dedup.is_duplicate("test")


# ---------------------------------------------------------------------------
# 7. Back-Pressure Hysteresis
# ---------------------------------------------------------------------------


class TestBackPressureHysteresis:
    """Verify hysteresis-based flow control stability."""

    def test_no_oscillation_in_dead_zone(self):
        from async_pipeline import BackPressureController
        bp = BackPressureController(high_water=0.8, low_water=0.6)

        # Start paused
        bp.update(800, 1000)  # 0.8 → pause
        assert bp.should_pause()

        # Pressure in dead zone — should remain paused
        bp.update(700, 1000)  # 0.7 → dead zone
        assert bp.should_pause()

        # Still in dead zone
        bp.update(650, 1000)  # 0.65 → dead zone
        assert bp.should_pause()

        # Below low water → resume
        bp.update(599, 1000)  # 0.599 → below low water
        assert bp.should_resume()

    def test_pause_at_high_water(self):
        from async_pipeline import BackPressureController
        bp = BackPressureController(high_water=0.8, low_water=0.6)
        bp.update(500, 1000)
        assert bp.should_resume()
        bp.update(800, 1000)
        assert bp.should_pause()

    def test_resume_at_low_water(self):
        from async_pipeline import BackPressureController
        bp = BackPressureController(high_water=0.8, low_water=0.6)
        bp.update(900, 1000)
        assert bp.should_pause()
        bp.update(600, 1000)
        assert bp.should_resume()

    def test_zero_max_tokens(self):
        from async_pipeline import BackPressureController
        bp = BackPressureController()
        bp.update(100, 0)
        assert bp.should_pause()

    def test_pressure_property(self):
        from async_pipeline import BackPressureController
        bp = BackPressureController()
        bp.update(750, 1000)
        assert abs(bp.pressure - 0.75) < 1e-9

    def test_validation(self):
        from async_pipeline import BackPressureController
        with pytest.raises(ValueError):
            BackPressureController(high_water=0.5, low_water=0.8)

    def test_rapid_oscillation_stability(self):
        """Simulate rapid pressure oscillation — should not toggle."""
        from async_pipeline import BackPressureController
        bp = BackPressureController(high_water=0.8, low_water=0.6)

        # Oscillate in dead zone
        bp.update(800, 1000)  # pause
        for _ in range(100):
            bp.update(700, 1000)  # dead zone
            assert bp.should_pause(), "Should remain paused in dead zone"


# ---------------------------------------------------------------------------
# 8. Task Scheduling
# ---------------------------------------------------------------------------


class TestTaskScheduling:
    """Verify task decomposition and scheduling correctness."""

    def test_decompose_creates_tasks(self):
        from coordinator import TaskDecomposer
        d = TaskDecomposer()
        tasks = d.decompose("Fix the bug and then test it")
        assert len(tasks) >= 1

    def test_decompose_infers_capabilities(self):
        from coordinator import TaskDecomposer
        d = TaskDecomposer()
        tasks = d.decompose("Implement the new API endpoint")
        assert "code" in tasks[0].required_capabilities

    def test_schedule_respects_dependencies(self):
        from coordinator import TaskScheduler, TaskSpec, AgentProfile, AgentRole, TaskStatus
        agent = AgentProfile(
            role=AgentRole.WORKER,
            name="worker",
            capabilities=["code", "test"],
        )
        scheduler = TaskScheduler([agent])

        t1 = TaskSpec(description="task 1", required_capabilities=["code"])
        t2 = TaskSpec(description="task 2", required_capabilities=["test"],
                      dependencies=[t1.id])
        tasks = [t1, t2]

        assignments = scheduler.schedule(tasks)

        # t2 should not be assigned until t1 is assigned
        assert t1.status == TaskStatus.ASSIGNED
        # t2's dep is on t1, which is now assigned
        # The scheduler runs in a loop, so t2 should also be assigned
        assigned_count = sum(1 for t in tasks if t.status == TaskStatus.ASSIGNED)
        assert assigned_count >= 1

    def test_schedule_only_uses_workers(self):
        from coordinator import (TaskScheduler, TaskSpec, AgentProfile,
                                  AgentRole, TaskStatus)
        orchestrator = AgentProfile(
            role=AgentRole.ORCHESTRATOR,
            name="orch",
            capabilities=["code"],
        )
        scheduler = TaskScheduler([orchestrator])
        t = TaskSpec(description="task", required_capabilities=["code"])
        scheduler.schedule([t])
        # ORCHESTRATOR should not be assigned
        assert t.status == TaskStatus.PENDING

    def test_schedule_load_balancing(self):
        from coordinator import (TaskScheduler, TaskSpec, AgentProfile,
                                  AgentRole, TaskStatus)
        a1 = AgentProfile(role=AgentRole.WORKER, name="w1",
                          capabilities=["code"], max_tasks=3)
        a2 = AgentProfile(role=AgentRole.WORKER, name="w2",
                          capabilities=["code"], max_tasks=3)
        scheduler = TaskScheduler([a1, a2])

        tasks = [
            TaskSpec(description=f"task {i}", required_capabilities=["code"])
            for i in range(4)
        ]
        scheduler.schedule(tasks)

        # Both agents should have tasks
        assert a1.active_tasks > 0
        assert a2.active_tasks > 0

    def test_complexity_estimation(self):
        from coordinator import TaskDecomposer, TaskSpec
        simple = TaskSpec(description="fix it", required_capabilities=["code"])
        # score = 2 words + 1 cap*5 = 7 → "low"
        assert TaskDecomposer.estimate_complexity(simple) == "low"
        # score = 9 words + 3 caps*5 = 24 → "medium"
        medium_task = TaskSpec(
            description="implement the comprehensive testing framework for the API",
            required_capabilities=["code", "test", "design"],
        )
        assert TaskDecomposer.estimate_complexity(medium_task) == "medium"
        # Need score >= 30 for "high": 16 words + 3 caps*5 = 31
        complex_task = TaskSpec(
            description="implement the comprehensive testing framework for the entire API including all edge cases and error handling",
            required_capabilities=["code", "test", "design"],
        )
        assert TaskDecomposer.estimate_complexity(complex_task) == "high"


# ---------------------------------------------------------------------------
# Integration: Token estimation across all modules
# ---------------------------------------------------------------------------


class TestCrossModuleConsistency:
    """Ensure token estimation is consistent across all modules."""

    def test_all_modules_agree_on_sample_text(self):
        from token_utils import estimate_tokens
        from context_compressor_v2 import _estimate_tokens
        from tool_result_manager import TokenEstimator

        sample = "Hello, this is a test of the emergency broadcast system."
        t1 = estimate_tokens(sample)
        t2 = _estimate_tokens(sample)
        t3 = TokenEstimator.estimate_tokens(sample)
        assert t1 == t2 == t3, f"Mismatch: token_utils={t1}, compressor={t2}, result_mgr={t3}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
