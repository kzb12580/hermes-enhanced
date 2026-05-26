"""Smart Retry Manager for Hermes Agent.

Provides intelligent retry logic for failed tool calls with:
- Error classification (transient vs permanent)
- Exponential backoff with jitter
- Per-tool retry policies
- Circuit breaker pattern to avoid hammering broken tools
- Budget-aware retry (won't retry if token budget is low)

FEATURE GAP FIXED: The existing ToolOrchestrator has no retry mechanism.
When a tool call fails (network timeout, rate limit, transient error),
the failure is final. In production, many tool failures are transient
and a single retry with backoff would succeed.

Usage:
    retry_mgr = SmartRetryManager()
    result = retry_mgr.execute_with_retry(
        tool_call=ToolCall(name="web_extract", args={"url": "..."}),
        executor_fn=my_executor,
    )
"""

from __future__ import annotations

import random
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

try:
    from .tool_orchestrator import ToolCall, BatchResult
except ImportError:
    from tool_orchestrator import ToolCall, BatchResult


# ---------------------------------------------------------------------------
# Error Classification
# ---------------------------------------------------------------------------


class ErrorCategory(Enum):
    """Classification of tool execution errors."""
    TRANSIENT = auto()    # Retry likely to succeed
    PERMANENT = auto()    # Retry won't help
    RATE_LIMITED = auto() # Need to wait, then retry
    UNKNOWN = auto()      # Unclassified


# Patterns that indicate transient errors
_TRANSIENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"timeout", re.I),
    re.compile(r"timed?\s*out", re.I),
    re.compile(r"connection\s+(?:reset|refused|aborted|closed)", re.I),
    re.compile(r"temporary", re.I),
    re.compile(r"network\s+(?:error|unreachable)", re.I),
    re.compile(r"ECONNRESET"),
    re.compile(r"ECONNREFUSED"),
    re.compile(r"ETIMEDOUT"),
    re.compile(r"socket\s+(?:error|timeout)", re.I),
    re.compile(r"502\s+Bad\s+Gateway", re.I),
    re.compile(r"503\s+Service\s+Unavailable", re.I),
    re.compile(r"504\s+Gateway\s+Timeout", re.I),
    re.compile(r"\b520\b"),
    re.compile(r"\b521\b"),
    re.compile(r"\b522\b"),
    re.compile(r"\b523\b"),
    re.compile(r"\b524\b"),
    re.compile(r"429\s+Too\s+Many\s+Requests", re.I),
    re.compile(r"rate\s+limit", re.I),
    re.compile(r"temporarily\s+unavailable", re.I),
    re.compile(r"try\s+again", re.I),
    re.compile(r"server\s+error", re.I),
    re.compile(r"internal\s+error", re.I),
    re.compile(r"ENOTFOUND"),
    re.compile(r"handshake\s+timeout", re.I),
]

# Patterns that indicate permanent errors (no point retrying)
_PERMANENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"not\s+found", re.I),
    re.compile(r"\b404\b"),
    re.compile(r"forbidden", re.I),
    re.compile(r"\b403\b"),
    re.compile(r"unauthorized", re.I),
    re.compile(r"\b401\b"),
    re.compile(r"permission\s+denied", re.I),
    re.compile(r"access\s+denied", re.I),
    re.compile(r"invalid\s+(?:argument|parameter|input)", re.I),
    re.compile(r"syntax\s+error", re.I),
    re.compile(r"no\s+such\s+file", re.I),
    re.compile(r"file\s+not\s+found", re.I),
    re.compile(r"ValueError", re.I),
    re.compile(r"TypeError", re.I),
    re.compile(r"KeyError", re.I),
    re.compile(r"AttributeError", re.I),
    re.compile(r"ImportError", re.I),
    re.compile(r"ModuleNotFoundError", re.I),
]

# Rate-limit specific patterns
_RATE_LIMIT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b429\b"),
    re.compile(r"rate\s*limit", re.I),
    re.compile(r"too\s+many\s+requests", re.I),
    re.compile(r"quota\s+exceeded", re.I),
    re.compile(r"throttl", re.I),
    re.compile(r"retry.after", re.I),
]


def classify_error(error_message: str) -> ErrorCategory:
    """Classify an error message into a category.

    Parameters
    ----------
    error_message : str
        The error string to classify.

    Returns
    -------
    ErrorCategory enum value.
    """
    if not error_message:
        return ErrorCategory.UNKNOWN

    # Check rate limit first (most specific)
    for pat in _RATE_LIMIT_PATTERNS:
        if pat.search(error_message):
            return ErrorCategory.RATE_LIMITED

    # Check permanent errors (should not retry)
    for pat in _PERMANENT_PATTERNS:
        if pat.search(error_message):
            return ErrorCategory.PERMANENT

    # Check transient errors (good candidates for retry)
    for pat in _TRANSIENT_PATTERNS:
        if pat.search(error_message):
            return ErrorCategory.TRANSIENT

    return ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Retry Policies
# ---------------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Configuration for retry behavior.

    Attributes
    ----------
    max_retries : int
        Maximum number of retry attempts.
    base_delay : float
        Base delay in seconds before first retry.
    max_delay : float
        Maximum delay between retries (cap for exponential backoff).
    backoff_factor : float
        Multiplier for exponential backoff.
    jitter : float
        Random jitter range (0-1) added to delay.
    retryable_categories : set[ErrorCategory]
        Which error categories should trigger retries.
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    jitter: float = 0.25
    retryable_categories: set[ErrorCategory] = field(
        default_factory=lambda: {
            ErrorCategory.TRANSIENT,
            ErrorCategory.RATE_LIMITED,
            ErrorCategory.UNKNOWN,
        }
    )


# Default per-tool policies
_DEFAULT_POLICIES: dict[str, RetryPolicy] = {
    "web_extract": RetryPolicy(max_retries=3, base_delay=2.0, backoff_factor=2.0),
    "web_search": RetryPolicy(max_retries=3, base_delay=2.0, backoff_factor=2.0),
    "terminal": RetryPolicy(max_retries=1, base_delay=0.5, backoff_factor=1.0),
    "read_file": RetryPolicy(max_retries=2, base_delay=0.5, backoff_factor=1.5),
    "search_files": RetryPolicy(max_retries=2, base_delay=0.5, backoff_factor=1.5),
    "default": RetryPolicy(max_retries=2, base_delay=1.0, backoff_factor=2.0),
}


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation — requests flow through
    OPEN = "open"           # Too many failures — requests are blocked
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreaker:
    """Per-tool circuit breaker to avoid hammering broken tools.

    After `failure_threshold` consecutive failures, the circuit opens
    and blocks further attempts for `recovery_timeout` seconds.

    Parameters
    ----------
    failure_threshold : int
        Consecutive failures before opening the circuit.
    recovery_timeout : float
        Seconds to wait before trying again (half-open).
    """
    failure_threshold: int = 5
    recovery_timeout: float = 60.0

    # Internal state
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0

    def __post_init__(self) -> None:
        self._lock = threading.Lock()  # noqa: no-member
        self._probe_sent: bool = False

    def record_success(self) -> None:
        """Record a successful execution — reset the circuit."""
        with self._lock:
            self.consecutive_failures = 0
            self.state = CircuitState.CLOSED
            self.last_success_time = time.time()
            self._probe_sent = False

    def record_failure(self) -> None:
        """Record a failed execution — may open the circuit."""
        with self._lock:
            self.consecutive_failures += 1
            self.last_failure_time = time.time()
            if self.consecutive_failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self._probe_sent = False  # Reset for next HALF_OPEN cycle

    def allow_request(self) -> bool:
        """Check if a request should be allowed through.

        Returns
        -------
        True if the request should proceed, False if circuit is open.
        """
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self._probe_sent = True  # This request IS the probe
                    return True
                return False

            # HALF_OPEN — only allow one probe request.
            # NOTE: _probe_sent is already True from the OPEN→HALF_OPEN
            # transition above (that transition *is* the probe), so this
            # branch correctly blocks all subsequent requests while the
            # probe is in-flight.  record_success() / record_failure()
            # will transition out of HALF_OPEN and reset _probe_sent.
            if not self._probe_sent:
                self._probe_sent = True
                return True
            return False

    def reset(self) -> None:
        """Manually reset the circuit to closed state."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0
            self._probe_sent = False


# ---------------------------------------------------------------------------
# Retry Result
# ---------------------------------------------------------------------------


@dataclass
class RetryResult:
    """Result of a retry-managed execution.

    Contains the final result along with retry metadata.
    """
    result: Any = None
    success: bool = False
    error: str | None = None
    attempts: int = 1
    retries: int = 0
    total_delay: float = 0.0
    error_category: ErrorCategory = ErrorCategory.UNKNOWN
    circuit_state: str = "closed"
    history: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SmartRetryManager
# ---------------------------------------------------------------------------


class SmartRetryManager:
    """Manages retry logic for tool execution with circuit breakers.

    Parameters
    ----------
    policies : dict[str, RetryPolicy] | None
        Per-tool retry policies. Falls back to defaults.
    time_fn : Callable[[], float] | None
        Time function (injectable for testing). Defaults to time.time().
    sleep_fn : Callable[[float], None] | None
        Sleep function (injectable for testing). Defaults to time.sleep().
    """

    def __init__(
        self,
        policies: dict[str, RetryPolicy] | None = None,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._policies = {**_DEFAULT_POLICIES, **(policies or {})}
        self._time_fn = time_fn or time.time
        self._sleep_fn = sleep_fn or time.sleep
        self._circuits: dict[str, CircuitBreaker] = {}
        self._circuit_lock = threading.Lock()
        self._stats_lock = threading.Lock()

        # Stats
        self._stats = {
            "total_executions": 0,
            "total_retries": 0,
            "total_successes": 0,
            "total_failures": 0,
            "circuit_blocks": 0,
        }

    def get_policy(self, tool_name: str) -> RetryPolicy:
        """Get the retry policy for a tool."""
        return self._policies.get(tool_name, self._policies.get("default", RetryPolicy()))

    def get_circuit(self, tool_name: str) -> CircuitBreaker:
        """Get or create the circuit breaker for a tool.

        Uses double-checked locking to avoid creating duplicate breakers
        under concurrent access.
        """
        cb = self._circuits.get(tool_name)
        if cb is None:
            with self._circuit_lock:
                cb = self._circuits.get(tool_name)
                if cb is None:
                    cb = CircuitBreaker()
                    self._circuits[tool_name] = cb
        return cb

    def execute_with_retry(
        self,
        tool_call: ToolCall,
        executor_fn: Callable[[ToolCall], Any],
        budget_check: Callable[[], bool] | None = None,
    ) -> RetryResult:
        """Execute a tool call with retry logic.

        Parameters
        ----------
        tool_call : ToolCall
            The tool call to execute.
        executor_fn : Callable
            Function that executes the tool call.
        budget_check : Callable[[], bool] | None
            Optional function that returns True if there's budget for retry.

        Returns
        -------
        RetryResult with final result and retry metadata.
        """
        with self._stats_lock:
            self._stats["total_executions"] += 1
        policy = self.get_policy(tool_call.name)
        circuit = self.get_circuit(tool_call.name)
        history: list[dict] = []
        total_delay = 0.0

        for attempt in range(policy.max_retries + 1):
            # Check circuit breaker
            if not circuit.allow_request():
                with self._stats_lock:
                    self._stats["circuit_blocks"] += 1
                return RetryResult(
                    success=False,
                    error=f"Circuit breaker OPEN for {tool_call.name}",
                    attempts=attempt,
                    retries=attempt,
                    total_delay=total_delay,
                    error_category=ErrorCategory.TRANSIENT,
                    circuit_state=circuit.state.value,
                    history=history,
                )

            # Execute
            t0 = self._time_fn()
            try:
                result = executor_fn(tool_call)
                elapsed = self._time_fn() - t0
                # Check if result indicates a returned failure (e.g. has success=False)
                if hasattr(result, 'success') and result.success is False:
                    # Treat as failure for retry purposes
                    error_msg = getattr(result, 'error', '') or 'Tool returned failure'
                    category = classify_error(str(error_msg))
                    circuit.record_failure()
                    history.append({
                        "attempt": attempt + 1,
                        "success": False,
                        "error": str(error_msg),
                        "category": category.name,
                        "elapsed": elapsed,
                    })
                    should_retry = (
                        attempt < policy.max_retries
                        and category in policy.retryable_categories
                    )
                    if not should_retry:
                        with self._stats_lock:
                            self._stats["total_failures"] += 1
                        return RetryResult(
                            error=str(error_msg),
                            success=False,
                            result=result,
                            attempts=attempt + 1,
                            retries=attempt,
                            total_delay=total_delay,
                            error_category=category,
                            circuit_state=circuit.state.value,
                            history=history,
                        )
                    # Calculate backoff delay
                    delay = self._calculate_delay(policy, attempt)
                    total_delay += delay
                    with self._stats_lock:
                        self._stats["total_retries"] += 1
                    self._sleep_fn(delay)
                    continue

                # Success!
                circuit.record_success()
                with self._stats_lock:
                    self._stats["total_successes"] += 1
                history.append({
                    "attempt": attempt + 1,
                    "success": True,
                    "elapsed": elapsed,
                })

                # Report first error category if this was a retry
                first_error_cat = ErrorCategory.UNKNOWN
                if history and attempt > 0:
                    first_error_cat = ErrorCategory[history[0].get("category", "UNKNOWN")]

                return RetryResult(
                    result=result,
                    success=True,
                    attempts=attempt + 1,
                    retries=attempt,
                    total_delay=total_delay,
                    error_category=first_error_cat,
                    circuit_state=circuit.state.value,
                    history=history,
                )
            except Exception as exc:
                elapsed = self._time_fn() - t0
                error_msg = str(exc)
                category = classify_error(error_msg)
                circuit.record_failure()

                history.append({
                    "attempt": attempt + 1,
                    "success": False,
                    "error": error_msg,
                    "category": category.name,
                    "elapsed": elapsed,
                })

                # Check if we should retry
                # Guard: if the same error repeats on every attempt, stop early
                if len(history) >= 2 and all(
                    h.get("error") == error_msg for h in history
                ):
                    should_retry = False
                else:
                    should_retry = (
                        attempt < policy.max_retries
                        and category in policy.retryable_categories
                    )

                if not should_retry:
                    with self._stats_lock:
                        self._stats["total_failures"] += 1
                    return RetryResult(
                        error=error_msg,
                        success=False,
                        attempts=attempt + 1,
                        retries=attempt,
                        total_delay=total_delay,
                        error_category=category,
                        circuit_state=circuit.state.value,
                        history=history,
                    )

                # Check budget before retrying
                if budget_check and not budget_check():
                    with self._stats_lock:
                        self._stats["total_failures"] += 1
                    return RetryResult(
                        error=f"{error_msg} (retry skipped: insufficient budget)",
                        success=False,
                        attempts=attempt + 1,
                        retries=attempt,
                        total_delay=total_delay,
                        error_category=category,
                        circuit_state=circuit.state.value,
                        history=history,
                    )

                # Calculate backoff delay
                delay = self._calculate_delay(policy, attempt)
                total_delay += delay
                with self._stats_lock:
                    self._stats["total_retries"] += 1
                self._sleep_fn(delay)

        # Should not reach here, but handle gracefully
        with self._stats_lock:
            self._stats["total_failures"] += 1
        return RetryResult(
            error="Exhausted all retries",
            success=False,
            attempts=policy.max_retries + 1,
            retries=policy.max_retries,
            total_delay=total_delay,
            circuit_state=circuit.state.value,
            history=history,
        )

    def get_stats(self) -> dict[str, int]:
        """Return execution statistics."""
        return dict(self._stats)

    def get_circuit_states(self) -> dict[str, str]:
        """Return current state of all circuit breakers."""
        return {name: cb.state.value for name, cb in self._circuits.items()}

    def reset_circuit(self, tool_name: str) -> bool:
        """Manually reset a circuit breaker.

        Returns True if the circuit was found and reset.
        """
        circuit = self._circuits.get(tool_name)
        if circuit:
            circuit.reset()
            return True
        return False

    def reset_all(self) -> None:
        """Reset all state."""
        for circuit in self._circuits.values():
            circuit.reset()
        with self._stats_lock:
            for key in self._stats:
                self._stats[key] = 0

    # -- Internals -----------------------------------------------------------

    def _calculate_delay(self, policy: RetryPolicy, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = policy.base_delay * (policy.backoff_factor ** attempt)
        delay = min(delay, policy.max_delay)
        # Add jitter
        jitter_range = delay * policy.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        # Enforce minimum delay of 50ms
        return max(0.05, delay)
