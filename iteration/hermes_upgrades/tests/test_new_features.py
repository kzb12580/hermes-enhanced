"""Tests for the 3 new feature modules:

1. TokenBudgetManager - session-level token budget tracking
2. SmartRetryManager - intelligent retry with circuit breakers
3. ToolResultSummarizer - structure-aware result summarization
"""

from __future__ import annotations

import sys
import os
import time
from pathlib import Path

import pytest

# Ensure imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================================================
# 1. TokenBudgetManager tests
# ============================================================================

from token_budget_manager import (
    TokenBudgetManager,
    PressureZone,
    AllocationResult,
    BudgetSnapshot,
    TurnRecord,
    PRESSURE_GREEN,
    PRESSURE_YELLOW,
    PRESSURE_ORANGE,
    PRESSURE_RED,
)


class TestTokenBudgetManager:
    """Tests for TokenBudgetManager."""

    def test_init_default(self):
        """Default initialization with standard parameters."""
        mgr = TokenBudgetManager()
        assert mgr.session_budget == 160_000
        assert mgr.model_limit == 200_000
        assert mgr.reserve_tokens == 20_000

    def test_init_custom(self):
        """Custom initialization parameters."""
        mgr = TokenBudgetManager(session_budget=80_000, model_limit=100_000)
        assert mgr.session_budget == 80_000

    def test_init_budget_capped_at_model_limit(self):
        """Session budget cannot exceed model limit."""
        mgr = TokenBudgetManager(session_budget=300_000, model_limit=200_000)
        assert mgr.session_budget == 200_000

    def test_init_validation(self):
        """Invalid parameters raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            TokenBudgetManager(session_budget=0)
        with pytest.raises(ValueError, match="positive"):
            TokenBudgetManager(model_limit=-1)
        with pytest.raises(ValueError, match="non-negative"):
            TokenBudgetManager(reserve_tokens=-1)

    def test_initial_pressure_zero(self):
        """Initial pressure should be zero."""
        mgr = TokenBudgetManager()
        assert mgr.pressure == 0.0
        assert mgr.pressure_zone == PressureZone.GREEN

    def test_allocate_default_tool(self):
        """Allocate tokens for a tool with default budget."""
        mgr = TokenBudgetManager()
        result = mgr.allocate("read_file")
        assert isinstance(result, AllocationResult)
        assert result.tool_name == "read_file"
        assert result.requested_tokens == 15_000
        assert result.allocated_tokens > 0
        assert result.pressure_zone == PressureZone.GREEN
        assert result.reduction_factor == 1.0

    def test_allocate_unknown_tool(self):
        """Unknown tool gets default budget."""
        mgr = TokenBudgetManager()
        result = mgr.allocate("unknown_tool")
        assert result.requested_tokens == 8_000  # default budget

    def test_allocate_custom_requested(self):
        """Custom requested tokens override tool default."""
        mgr = TokenBudgetManager()
        result = mgr.allocate("read_file", requested_tokens=5_000)
        assert result.requested_tokens == 5_000

    def test_record_usage_tracking(self):
        """Recording usage tracks tokens correctly."""
        mgr = TokenBudgetManager()
        mgr.begin_turn(1)
        mgr.record_usage("read_file", 10_000)
        mgr.record_usage("terminal", 5_000)

        assert mgr.used_tokens == 15_000
        assert mgr.remaining_tokens == 160_000 - 15_000

    def test_turn_lifecycle(self):
        """Begin and end turn lifecycle."""
        mgr = TokenBudgetManager()
        mgr.begin_turn(1)
        mgr.record_usage("read_file", 10_000)
        record = mgr.end_turn()

        assert record is not None
        assert record.turn_number == 1
        assert record.total_tokens == 10_000
        assert "read_file" in record.tool_usages

    def test_multiple_turns(self):
        """Multiple turns accumulate usage."""
        mgr = TokenBudgetManager()
        for i in range(5):
            mgr.begin_turn(i + 1)
            mgr.record_usage("read_file", 10_000)
            mgr.end_turn()

        assert mgr.used_tokens == 50_000
        assert len(mgr.get_turn_history()) == 5

    def test_pressure_zones(self):
        """Pressure transitions through zones correctly."""
        mgr = TokenBudgetManager(session_budget=100_000)

        # Green zone
        mgr.begin_turn(1)
        mgr.record_usage("tool", 50_000)
        mgr.end_turn()
        assert mgr.pressure_zone == PressureZone.GREEN

        # Yellow zone
        mgr.begin_turn(2)
        mgr.record_usage("tool", 25_000)
        mgr.end_turn()
        assert mgr.pressure_zone == PressureZone.YELLOW

        # Orange zone
        mgr.begin_turn(3)
        mgr.record_usage("tool", 15_000)
        mgr.end_turn()
        assert mgr.pressure_zone == PressureZone.ORANGE

    def test_allocate_reduced_in_yellow_zone(self):
        """Yellow zone reduces allocations moderately."""
        mgr = TokenBudgetManager(session_budget=100_000)
        mgr.begin_turn(1)
        mgr.record_usage("tool", 72_000)
        mgr.end_turn()

        result = mgr.allocate("read_file")
        assert result.reduction_factor == 0.8
        assert result.pressure_zone == PressureZone.YELLOW

    def test_allocate_reduced_in_orange_zone(self):
        """Orange zone reduces allocations aggressively."""
        mgr = TokenBudgetManager(session_budget=100_000)
        mgr.begin_turn(1)
        mgr.record_usage("tool", 87_000)
        mgr.end_turn()

        result = mgr.allocate("read_file")
        assert result.reduction_factor == 0.5
        assert result.pressure_zone == PressureZone.ORANGE

    def test_allocate_reduced_in_red_zone(self):
        """Red zone reduces allocations severely."""
        mgr = TokenBudgetManager(session_budget=100_000)
        mgr.begin_turn(1)
        mgr.record_usage("tool", 96_000)
        mgr.end_turn()

        result = mgr.allocate("read_file")
        assert result.reduction_factor == 0.25
        assert result.pressure_zone == PressureZone.RED

    def test_allocate_exceeded_zone(self):
        """Exceeded zone returns minimal allocation."""
        mgr = TokenBudgetManager(session_budget=100_000)
        mgr.begin_turn(1)
        mgr.record_usage("tool", 101_000)
        mgr.end_turn()

        result = mgr.allocate("read_file")
        assert result.pressure_zone == PressureZone.EXCEEDED
        assert result.allocated_tokens <= 500

    def test_allocate_minimum_tokens(self):
        """Allocations have a minimum floor."""
        mgr = TokenBudgetManager(session_budget=100_000)
        # Fill up most of the budget
        mgr.begin_turn(1)
        mgr.record_usage("tool", 89_000)
        mgr.end_turn()

        result = mgr.allocate("read_file", requested_tokens=500)
        # Should still get at least 200 tokens
        assert result.allocated_tokens >= 200

    def test_get_snapshot(self):
        """BudgetSnapshot reflects current state."""
        mgr = TokenBudgetManager(session_budget=100_000)
        mgr.begin_turn(1)
        mgr.record_usage("tool", 25_000)

        snap = mgr.get_snapshot()
        assert isinstance(snap, BudgetSnapshot)
        assert snap.session_budget == 100_000
        assert snap.used_tokens == 25_000
        assert snap.remaining_tokens == 75_000
        assert snap.turn_count == 0  # turn not ended yet

    def test_estimate_turns_remaining(self):
        """Estimate turns remaining based on average."""
        mgr = TokenBudgetManager(session_budget=100_000)
        for i in range(5):
            mgr.begin_turn(i + 1)
            mgr.record_usage("tool", 10_000)
            mgr.end_turn()

        # Used 50K, 50K remaining, 10K per turn = 5 turns
        remaining = mgr.estimate_turns_remaining()
        assert abs(remaining - 5.0) < 0.1

    def test_estimate_turns_no_history(self):
        """Estimate returns infinity with no history."""
        mgr = TokenBudgetManager()
        assert mgr.estimate_turns_remaining() == float("inf")

    def test_suggest_compression(self):
        """Suggest compression in high-pressure zones."""
        mgr = TokenBudgetManager(session_budget=100_000)
        assert mgr.suggest_compression() is False

        mgr.begin_turn(1)
        mgr.record_usage("tool", 87_000)
        mgr.end_turn()
        assert mgr.suggest_compression() is True

    def test_reset(self):
        """Reset clears all state."""
        mgr = TokenBudgetManager()
        mgr.begin_turn(1)
        mgr.record_usage("tool", 50_000)
        mgr.end_turn()

        mgr.reset()
        assert mgr.used_tokens == 0
        assert mgr.remaining_tokens == 160_000
        assert len(mgr.get_turn_history()) == 0

    def test_end_turn_without_begin(self):
        """Ending a turn without beginning returns None."""
        mgr = TokenBudgetManager()
        assert mgr.end_turn() is None

    def test_record_usage_without_turn(self):
        """Recording usage outside a turn is a no-op."""
        mgr = TokenBudgetManager()
        mgr.record_usage("tool", 10_000)  # Should not raise
        assert mgr.used_tokens == 0

    def test_custom_tool_budgets(self):
        """Custom tool budgets override defaults."""
        mgr = TokenBudgetManager(tool_budgets={"my_tool": 30_000})
        result = mgr.allocate("my_tool")
        assert result.requested_tokens == 30_000

    def test_pressure_stays_bounded(self):
        """Pressure never exceeds 1.0."""
        mgr = TokenBudgetManager(session_budget=100)
        mgr.begin_turn(1)
        mgr.record_usage("tool", 999_999)
        assert mgr.pressure <= 1.0


# ============================================================================
# 2. SmartRetryManager tests
# ============================================================================

from smart_retry import (
    SmartRetryManager,
    RetryPolicy,
    RetryResult,
    CircuitBreaker,
    CircuitState,
    ErrorCategory,
    classify_error,
)
from tool_orchestrator import ToolCall, BatchResult


class TestErrorClassification:
    """Tests for error classification logic."""

    def test_classify_timeout(self):
        assert classify_error("Connection timed out") == ErrorCategory.TRANSIENT

    def test_classify_connection_reset(self):
        assert classify_error("ECONNRESET") == ErrorCategory.TRANSIENT

    def test_classify_rate_limit(self):
        assert classify_error("429 Too Many Requests") == ErrorCategory.RATE_LIMITED

    def test_classify_rate_limit_text(self):
        assert classify_error("rate limit exceeded") == ErrorCategory.RATE_LIMITED

    def test_classify_not_found(self):
        assert classify_error("File not found") == ErrorCategory.PERMANENT

    def test_classify_404(self):
        assert classify_error("HTTP 404") == ErrorCategory.PERMANENT

    def test_classify_403(self):
        assert classify_error("HTTP 403 Forbidden") == ErrorCategory.PERMANENT

    def test_classify_permission_denied(self):
        assert classify_error("permission denied") == ErrorCategory.PERMANENT

    def test_classify_value_error(self):
        assert classify_error("ValueError: invalid input") == ErrorCategory.PERMANENT

    def test_classify_empty(self):
        assert classify_error("") == ErrorCategory.UNKNOWN

    def test_classify_none_handling(self):
        assert classify_error(None) == ErrorCategory.UNKNOWN

    def test_classify_502(self):
        assert classify_error("502 Bad Gateway") == ErrorCategory.TRANSIENT

    def test_classify_503(self):
        assert classify_error("503 Service Unavailable") == ErrorCategory.TRANSIENT

    def test_classify_try_again(self):
        assert classify_error("Please try again later") == ErrorCategory.TRANSIENT

    def test_classify_quota_exceeded(self):
        assert classify_error("quota exceeded") == ErrorCategory.RATE_LIMITED

    def test_classify_throttle(self):
        assert classify_error("request throttled") == ErrorCategory.RATE_LIMITED


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == CircuitState.CLOSED

    def test_recovery_timeout_transitions(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Immediately — still open
        assert cb.allow_request() is False

        # After timeout — half-open
        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0


class TestSmartRetryManager:
    """Tests for SmartRetryManager."""

    def test_successful_execution(self):
        """First-try success returns result."""
        mgr = SmartRetryManager()
        tc = ToolCall(name="read_file", args={"path": "/tmp/test"})

        result = mgr.execute_with_retry(tc, lambda tc: "success")
        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 1
        assert result.retries == 0

    def test_retry_on_transient_error(self):
        """Transient errors trigger retries."""
        call_count = 0

        def flaky_executor(tc):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection timed out")
            return "success"

        mgr = SmartRetryManager(
            sleep_fn=lambda _: None,  # no actual sleep in tests
        )
        tc = ToolCall(name="web_extract", args={"url": "http://example.com"})
        result = mgr.execute_with_retry(tc, flaky_executor)

        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 3
        assert result.retries == 2

    def test_no_retry_on_permanent_error(self):
        """Permanent errors do not trigger retries."""
        call_count = 0

        def permanent_fail(tc):
            nonlocal call_count
            call_count += 1
            raise FileNotFoundError("File not found: /tmp/nope")

        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="read_file", args={"path": "/tmp/nope"})
        result = mgr.execute_with_retry(tc, permanent_fail)

        assert result.success is False
        assert result.attempts == 1
        assert result.retries == 0
        assert result.error_category == ErrorCategory.PERMANENT
        assert call_count == 1

    def test_max_retries_exhausted(self):
        """All retries exhausted returns failure."""
        def always_fail(tc):
            raise ConnectionError("Connection timed out")

        policy = RetryPolicy(max_retries=2, base_delay=0.01, backoff_factor=1.0)
        mgr = SmartRetryManager(
            policies={"web_extract": policy},
            sleep_fn=lambda _: None,
        )
        tc = ToolCall(name="web_extract", args={})
        result = mgr.execute_with_retry(tc, always_fail)

        assert result.success is False
        assert result.attempts == 3  # 1 initial + 2 retries
        assert result.retries == 2

    def test_circuit_breaker_blocks_execution(self):
        """Open circuit breaker blocks execution."""
        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="web_extract", args={})

        # Open the circuit
        circuit = mgr.get_circuit("web_extract")
        circuit.state = CircuitState.OPEN
        circuit.last_failure_time = time.time() + 9999  # Far in the future

        result = mgr.execute_with_retry(tc, lambda tc: "should not run")
        assert result.success is False
        assert "Circuit breaker OPEN" in result.error

    def test_budget_check_prevents_retry(self):
        """Budget check can prevent retries."""
        call_count = 0

        def fail_once(tc):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("timeout")
            return "success"

        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="web_extract", args={})

        # Budget check says no
        result = mgr.execute_with_retry(tc, fail_once, budget_check=lambda: False)
        assert result.success is False
        assert "insufficient budget" in result.error
        assert call_count == 1

    def test_rate_limit_error_with_retry(self):
        """Rate-limited errors trigger retries."""
        call_count = 0

        def rate_limited_then_ok(tc):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 Too Many Requests")
            return "ok"

        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="web_extract", args={})
        result = mgr.execute_with_retry(tc, rate_limited_then_ok)

        assert result.success is True
        assert result.error_category == ErrorCategory.RATE_LIMITED

    def test_custom_policy(self):
        """Custom per-tool policies are respected."""
        call_count = 0

        def fail_then_succeed(tc):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise ConnectionError("timeout")
            return "done"

        # Custom policy: only 1 retry
        policy = RetryPolicy(max_retries=1, base_delay=0.01)
        mgr = SmartRetryManager(
            policies={"terminal": policy},
            sleep_fn=lambda _: None,
        )
        tc = ToolCall(name="terminal", args={})
        result = mgr.execute_with_retry(tc, fail_then_succeed)

        assert result.success is True
        assert result.attempts == 2

    def test_stats_tracking(self):
        """Stats are tracked correctly."""
        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="read_file", args={})

        mgr.execute_with_retry(tc, lambda tc: "ok")
        mgr.execute_with_retry(tc, lambda tc: "ok")

        stats = mgr.get_stats()
        assert stats["total_executions"] == 2
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 0

    def test_retry_history_recorded(self):
        """Each attempt is recorded in history."""
        call_count = 0

        def fail_once(tc):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("timeout")
            return "ok"

        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="web_extract", args={})
        result = mgr.execute_with_retry(tc, fail_once)

        assert len(result.history) == 2
        assert result.history[0]["success"] is False
        assert result.history[1]["success"] is True

    def test_circuit_states_reported(self):
        """Circuit states are reported correctly."""
        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="web_extract", args={})

        # Trigger some failures to create circuit state
        for _ in range(5):
            def fail(tc):
                raise ConnectionError("timeout")
            mgr.execute_with_retry(tc, fail)

        states = mgr.get_circuit_states()
        assert "web_extract" in states

    def test_reset_circuit(self):
        """Manual circuit reset works."""
        mgr = SmartRetryManager()
        circuit = mgr.get_circuit("test_tool")
        circuit.record_failure()
        circuit.record_failure()

        assert mgr.reset_circuit("test_tool") is True
        assert circuit.state == CircuitState.CLOSED
        assert mgr.reset_circuit("nonexistent") is False

    def test_reset_all(self):
        """Reset all clears everything."""
        mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="read_file", args={})
        mgr.execute_with_retry(tc, lambda tc: "ok")

        mgr.reset_all()
        stats = mgr.get_stats()
        assert stats["total_executions"] == 0

    def test_backoff_delay_calculation(self):
        """Backoff delay follows exponential pattern."""
        policy = RetryPolicy(base_delay=1.0, backoff_factor=2.0, jitter=0.0)
        mgr = SmartRetryManager()

        d0 = mgr._calculate_delay(policy, 0)
        d1 = mgr._calculate_delay(policy, 1)
        d2 = mgr._calculate_delay(policy, 2)

        assert abs(d0 - 1.0) < 0.01
        assert abs(d1 - 2.0) < 0.01
        assert abs(d2 - 4.0) < 0.01

    def test_max_delay_cap(self):
        """Delay is capped at max_delay."""
        policy = RetryPolicy(base_delay=1.0, backoff_factor=10.0, max_delay=5.0, jitter=0.0)
        mgr = SmartRetryManager()

        delay = mgr._calculate_delay(policy, 10)  # Would be huge without cap
        assert delay == 5.0


# ============================================================================
# 3. ToolResultSummarizer tests
# ============================================================================

from tool_result_summarizer import (
    ToolResultSummarizer,
    SummaryStrategy,
    SummaryResult,
    CodeFileSummarizer,
    TerminalSummarizer,
    SearchResultSummarizer,
    JsonSummarizer,
)


class TestCodeFileSummarizer:
    """Tests for CodeFileSummarizer."""

    def test_python_summarize_extracts_imports(self):
        """Python summarizer extracts import statements."""
        content = '''import os
import sys
from pathlib import Path
from typing import Optional

class MyClass:
    """My class docstring."""
    def __init__(self):
        pass

    def method(self):
        return 42

def my_function():
    pass
'''
        summarizer = CodeFileSummarizer()
        summary, preserved = summarizer.summarize_python(content, target_tokens=100)
        assert "import os" in summary
        assert "import sys" in summary
        assert "class" in summary or "MyClass" in summary
        assert "def" in summary or "method" in summary

    def test_python_summarize_preserves_signatures(self):
        """Python summarizer preserves function/class signatures."""
        content = '''def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers."""
    return a + b

class DataProcessor:
    """Process data efficiently."""
    def __init__(self, config: dict):
        self.config = config

    def process(self, data: list) -> list:
        return [self._transform(x) for x in data]

    def _transform(self, item):
        return item
'''
        summarizer = CodeFileSummarizer()
        summary, preserved = summarizer.summarize_python(content, target_tokens=50)
        assert "calculate_sum" in summary
        assert "DataProcessor" in summary

    def test_js_summarize_extracts_exports(self):
        """JS summarizer extracts export statements."""
        content = '''export function processData(items) {
    return items.map(item => transform(item));
}

export class DataManager {
    constructor(config) {
        this.config = config;
    }

    fetch(url) {
        return fetch(url);
    }
}

export default DataManager;
'''
        summarizer = CodeFileSummarizer()
        summary, preserved = summarizer.summarize_js(content, target_tokens=50)
        assert "export" in summary or "DataManager" in summary


class TestTerminalSummarizer:
    """Tests for TerminalSummarizer."""

    def test_extract_errors(self):
        """Terminal summarizer extracts error lines."""
        content = "\n".join([f"output line {i}" for i in range(500)]) + """
ERROR: package xyz not found
npm ERR! code E404
npm ERR! 404 Not Found

Build completed successfully
"""
        summarizer = TerminalSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=50)
        assert "ERROR" in summary or "ERR" in summary
        assert any("error" in p.lower() or "warning" in p.lower() or "last" in p.lower() for p in preserved)

    def test_preserves_last_lines(self):
        """Terminal summarizer keeps last lines."""
        lines = [f"output line {i}" for i in range(100)]
        content = "\n".join(lines)
        content += "\nFatal error: something broke"

        summarizer = TerminalSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=100)
        assert "last" in str(preserved).lower() or "Fatal error" in summary

    def test_short_output_returned_as_is(self):
        """Short output is returned without modification."""
        content = "Hello, world!"
        summarizer = TerminalSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=1000)
        assert summary == content

    def test_exit_code_extraction(self):
        """Exit code is extracted."""
        content = "Some output\nexit code: 1\n"
        summarizer = TerminalSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=10)
        assert "1" in summary


class TestSearchResultSummarizer:
    """Tests for SearchResultSummarizer."""

    def test_extract_file_paths(self):
        """Search summarizer extracts file paths."""
        content = """Found 5 matches in 3 files:
./src/main.py:10: def main():
./src/utils.py:5: import os
./tests/test_main.py:1: from src.main import main
"""
        summarizer = SearchResultSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=50)
        assert "file" in str(preserved).lower() or "src/main.py" in summary

    def test_short_results_returned(self):
        """Short search results are returned as-is."""
        content = "1 match found in ./test.py"
        summarizer = SearchResultSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=1000)
        assert summary == content


class TestJsonSummarizer:
    """Tests for JsonSummarizer."""

    def test_summarize_dict(self):
        """JSON summarizer extracts object structure."""
        content = '{"name": "test", "version": "1.0", "dependencies": {"foo": "^1.0", "bar": "^2.0"}, "scripts": {"test": "pytest", "build": "webpack"}}'
        summarizer = JsonSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=30)
        assert "keys" in summary.lower()
        assert "name" in summary

    def test_summarize_list(self):
        """JSON summarizer extracts array structure."""
        content = '[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, {"id": 3, "name": "Charlie"}]'
        summarizer = JsonSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=20)
        assert "3 items" in summary

    def test_non_json_fallback(self):
        """Non-JSON content uses fallback."""
        content = "This is not JSON at all, just some text."
        summarizer = JsonSummarizer()
        summary, preserved = summarizer.summarize(content, target_tokens=5)
        assert len(summary) > 0


class TestToolResultSummarizer:
    """Tests for the main ToolResultSummarizer."""

    def test_within_budget_no_change(self):
        """Content within budget is returned unchanged."""
        summarizer = ToolResultSummarizer()
        content = "Short content"
        result = summarizer.summarize("read_file", content, target_tokens=1000)
        assert result.content == content
        assert result.compression_ratio == 1.0

    def test_empty_content(self):
        """Empty content returns empty result."""
        summarizer = ToolResultSummarizer()
        result = summarizer.summarize("read_file", "", target_tokens=100)
        assert result.content == ""
        assert result.original_tokens == 0

    def test_python_code_strategy_selection(self):
        """Python files get CODE_FILE strategy."""
        summarizer = ToolResultSummarizer()
        content = "import os\nclass Foo:\n  pass\n" * 100  # Make it long
        result = summarizer.summarize(
            "read_file", content, target_tokens=50, file_path="test.py"
        )
        assert result.strategy == SummaryStrategy.CODE_FILE
        assert result.compression_ratio < 1.0

    def test_terminal_strategy_selection(self):
        """Terminal tool gets TERMINAL_OUTPUT strategy."""
        summarizer = ToolResultSummarizer()
        content = "line\n" * 1000
        result = summarizer.summarize("terminal", content, target_tokens=50)
        assert result.strategy == SummaryStrategy.TERMINAL_OUTPUT

    def test_search_strategy_selection(self):
        """Search tool gets SEARCH_RESULTS strategy."""
        summarizer = ToolResultSummarizer()
        content = "Found matches in files:\n./src/a.py\n./src/b.py\n" * 100
        result = summarizer.summarize("search_files", content, target_tokens=50)
        assert result.strategy == SummaryStrategy.SEARCH_RESULTS

    def test_json_strategy_selection(self):
        """JSON content gets JSON_DATA strategy."""
        summarizer = ToolResultSummarizer()
        data = '{"key": "value"}' * 200
        result = summarizer.summarize("read_file", data, target_tokens=50, file_path="data.json")
        assert result.strategy == SummaryStrategy.JSON_DATA

    def test_generic_strategy_fallback(self):
        """Unknown content uses GENERIC strategy."""
        summarizer = ToolResultSummarizer()
        content = "random text without structure\n" * 500
        result = summarizer.summarize("unknown_tool", content, target_tokens=50)
        assert result.strategy == SummaryStrategy.GENERIC

    def test_compression_ratio_valid(self):
        """Compression ratio is always valid."""
        summarizer = ToolResultSummarizer()
        content = "a" * 50000
        result = summarizer.summarize("read_file", content, target_tokens=50)
        assert 0.0 <= result.compression_ratio <= 1.0
        assert result.summarized_tokens <= result.original_tokens

    def test_key_info_preserved_populated(self):
        """key_info_preserved is always populated."""
        summarizer = ToolResultSummarizer()
        content = "import os\nprint('hello')\n" * 200
        result = summarizer.summarize(
            "read_file", content, target_tokens=50, file_path="test.py"
        )
        assert len(result.key_info_preserved) > 0

    def test_file_extension_detection(self):
        """File extension detection works correctly."""
        assert ToolResultSummarizer._get_extension("test.py") == ".py"
        assert ToolResultSummarizer._get_extension("test.tar.gz") == ".gz"
        assert ToolResultSummarizer._get_extension("noext") == ""
        assert ToolResultSummarizer._get_extension("/path/to/file.js") == ".js"

    def test_generic_summarize_preserves_head_and_tail(self):
        """Generic summarizer preserves head and tail."""
        summarizer = ToolResultSummarizer()
        lines = [f"line {i}" for i in range(1000)]
        content = "\n".join(lines)

        result = summarizer.summarize("read_file", content, target_tokens=50)
        # Should contain first and last lines
        assert "line 0" in result.content
        assert "omitted" in result.content.lower() or "999" in result.content

    def test_js_file_strategy(self):
        """JS files get CODE_FILE strategy with JS summarizer."""
        summarizer = ToolResultSummarizer()
        content = "export function test() {\n  return 42;\n}\n" * 200
        result = summarizer.summarize(
            "read_file", content, target_tokens=50, file_path="test.js"
        )
        assert result.strategy == SummaryStrategy.CODE_FILE

    def test_summary_result_fields(self):
        """SummaryResult has all expected fields."""
        summarizer = ToolResultSummarizer()
        content = "x" * 10000
        result = summarizer.summarize("read_file", content, target_tokens=50)

        assert hasattr(result, "content")
        assert hasattr(result, "strategy")
        assert hasattr(result, "original_tokens")
        assert hasattr(result, "summarized_tokens")
        assert hasattr(result, "compression_ratio")
        assert hasattr(result, "key_info_preserved")

    def test_json_auto_detection(self):
        """JSON content is auto-detected even without file extension."""
        import json
        data = {"items": [f"value_{i}" for i in range(200)], "count": 200}
        content = json.dumps(data)
        summarizer = ToolResultSummarizer()
        result = summarizer.summarize("read_file", content, target_tokens=50)
        assert result.strategy == SummaryStrategy.JSON_DATA

    def test_code_auto_detection(self):
        """Code patterns are auto-detected in content."""
        summarizer = ToolResultSummarizer()
        content = "def hello():\n    pass\n\ndef world():\n    pass\n" * 200
        result = summarizer.summarize("read_file", content, target_tokens=50)
        assert result.strategy == SummaryStrategy.CODE_FILE


# ============================================================================
# Integration tests
# ============================================================================


class TestFeatureIntegration:
    """Integration tests combining the new features."""

    def test_budget_aware_retry(self):
        """Retry manager respects budget manager decisions."""
        budget = TokenBudgetManager(session_budget=100_000)
        budget.begin_turn(1)
        budget.record_usage("tool", 85_000)  # Push into orange zone

        call_count = 0

        def fail_then_succeed(tc):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("timeout")
            return "ok"

        retry_mgr = SmartRetryManager(sleep_fn=lambda _: None)
        tc = ToolCall(name="web_extract", args={})

        # Budget check says we're in orange zone but still have budget
        def budget_check():
            return not budget.suggest_compression() or budget.remaining_tokens > 5000

        result = retry_mgr.execute_with_retry(tc, fail_then_succeed, budget_check=budget_check)
        assert result.success is True

    def test_summarize_then_track_budget(self):
        """Summarize result and track token usage in budget."""
        budget = TokenBudgetManager()
        summarizer = ToolResultSummarizer()

        budget.begin_turn(1)

        # Simulate a large tool result
        content = "import os\n" * 5000
        allocation = budget.allocate("read_file")
        result = summarizer.summarize(
            "read_file", content, target_tokens=allocation.allocated_tokens
        )

        budget.record_usage("read_file", result.summarized_tokens)
        budget.end_turn()

        # Verify tracking
        assert budget.used_tokens == result.summarized_tokens
        assert budget.used_tokens > 0
