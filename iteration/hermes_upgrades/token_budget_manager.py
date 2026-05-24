"""Token Budget Manager for Hermes Agent.

Tracks cumulative token usage across a conversation session, providing
dynamic per-tool budget adjustments when the session budget is running low.
Unlike ToolResultManager which manages per-result budgets, this module
manages the *session-level* token budget.

FEATURE GAP FIXED: The existing ToolResultManager has no concept of cumulative
budget across turns. Each process() call is independent. In production, a long
session can blow through the model's context window because no component tracks
total consumption.

Usage:
    budget = TokenBudgetManager(session_budget=160_000, model_limit=200_000)
    allocated = budget.allocate("read_file", requested_tokens=15000)
    # allocated might be less than requested if budget is tight
    budget.record_usage("read_file", actual_tokens=12000)
    pressure = budget.pressure  # 0.0 to 1.0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default per-tool token budgets (same as tool_result_manager for consistency)
DEFAULT_TOOL_BUDGETS: dict[str, int] = {
    "read_file": 15_000,
    "terminal": 10_000,
    "search_files": 8_000,
    "web_extract": 12_000,
    "default": 8_000,
}

# Budget pressure zones
PRESSURE_GREEN = 0.50   # < 50%: full budgets
PRESSURE_YELLOW = 0.70  # 50-70%: moderate reduction
PRESSURE_ORANGE = 0.85  # 70-85%: aggressive reduction
PRESSURE_RED = 0.95     # > 95%: emergency mode


class PressureZone(Enum):
    """Budget pressure zones that control allocation strategy."""
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    EXCEEDED = "exceeded"


@dataclass
class AllocationResult:
    """Result of a token allocation request."""
    tool_name: str
    requested_tokens: int
    allocated_tokens: int
    pressure_zone: PressureZone
    reduction_factor: float  # 1.0 = no reduction, 0.5 = halved
    reason: str


@dataclass
class TurnRecord:
    """Record of token usage for a single turn."""
    turn_number: int
    timestamp: float
    tool_usages: dict[str, int] = field(default_factory=dict)  # tool_name -> tokens
    total_tokens: int = 0


@dataclass
class BudgetSnapshot:
    """Point-in-time snapshot of budget state."""
    session_budget: int
    used_tokens: int
    remaining_tokens: int
    pressure: float
    pressure_zone: PressureZone
    turn_count: int
    avg_tokens_per_turn: float


# ---------------------------------------------------------------------------
# TokenBudgetManager
# ---------------------------------------------------------------------------


class TokenBudgetManager:
    """Session-level token budget manager with dynamic allocation.

    Tracks cumulative token usage across turns and provides dynamic
    per-tool budget adjustments based on remaining capacity.

    Parameters
    ----------
    session_budget : int
        Total tokens available for the session (default 160K).
    model_limit : int
        Hard model context limit (default 200K).
    tool_budgets : dict[str, int] | None
        Override default per-tool budgets.
    reserve_tokens : int
        Tokens to reserve for system prompt + response generation.
    """

    def __init__(
        self,
        session_budget: int = 160_000,
        model_limit: int = 200_000,
        tool_budgets: dict[str, int] | None = None,
        reserve_tokens: int = 20_000,
    ) -> None:
        if session_budget <= 0:
            raise ValueError("session_budget must be positive")
        if model_limit <= 0:
            raise ValueError("model_limit must be positive")
        if reserve_tokens < 0:
            raise ValueError("reserve_tokens must be non-negative")

        self.session_budget = min(session_budget, model_limit)
        self.model_limit = model_limit
        self.reserve_tokens = reserve_tokens
        self._tool_budgets = {**DEFAULT_TOOL_BUDGETS, **(tool_budgets or {})}

        # State
        self._used_tokens: int = 0
        self._turns: list[TurnRecord] = []
        self._current_turn: TurnRecord | None = None
        import threading
        self._lock = threading.RLock()

    # -- Public API ----------------------------------------------------------

    def begin_turn(self, turn_number: int) -> None:
        """Mark the start of a new turn."""
        with self._lock:
            self._current_turn = TurnRecord(
                turn_number=turn_number,
                timestamp=time.time(),
            )

    def end_turn(self) -> TurnRecord | None:
        """Mark the end of the current turn and finalize its record."""
        with self._lock:
            if self._current_turn is None:
                return None
            self._used_tokens += self._current_turn.total_tokens
            self._turns.append(self._current_turn)
            record = self._current_turn
            self._current_turn = None
            return record

    def allocate(
        self,
        tool_name: str,
        requested_tokens: int | None = None,
    ) -> AllocationResult:
        """Allocate tokens for a tool call based on current budget pressure.

        Parameters
        ----------
        tool_name : str
            Name of the tool requesting tokens.
        requested_tokens : int | None
            Tokens requested. If None, uses the tool's default budget.

        Returns
        -------
        AllocationResult with allocated count and pressure info.
        """
        base_budget = self._tool_budgets.get(
            tool_name, self._tool_budgets.get("default", 8_000)
        )
        requested = requested_tokens if requested_tokens is not None else base_budget

        zone = self.pressure_zone
        remaining = self.remaining_tokens

        # If already exceeded, return minimal allocation
        if zone == PressureZone.EXCEEDED:
            return AllocationResult(
                tool_name=tool_name,
                requested_tokens=requested,
                allocated_tokens=min(500, requested),
                pressure_zone=zone,
                reduction_factor=0.05,
                reason="Budget exceeded — emergency minimal allocation",
            )

        # Apply zone-based reduction
        factor = self._reduction_factor(zone)

        # Also consider absolute remaining capacity
        available = int(base_budget * factor)
        available = min(available, remaining, requested)

        # Never allocate less than 200 tokens (minimum useful result) or more than requested
        available = max(200, available) if remaining >= 200 else remaining
        available = min(available, requested)

        reason = f"Pressure zone {zone.value}: allocated {available}/{requested} tokens"
        if available < requested:
            reason += f" (reduced by {(1 - available/requested)*100:.0f}%)"

        return AllocationResult(
            tool_name=tool_name,
            requested_tokens=requested,
            allocated_tokens=available,
            pressure_zone=zone,
            reduction_factor=factor,
            reason=reason,
        )

    def record_usage(self, tool_name: str, actual_tokens: int) -> None:
        """Record actual token usage for a tool call in the current turn.

        Parameters
        ----------
        tool_name : str
            Name of the tool.
        actual_tokens : int
            Actual tokens consumed.
        """
        with self._lock:
            if self._current_turn is not None:
                self._current_turn.tool_usages[tool_name] = (
                    self._current_turn.tool_usages.get(tool_name, 0) + actual_tokens
                )
                self._current_turn.total_tokens += actual_tokens

    @property
    def used_tokens(self) -> int:
        """Total tokens used so far (completed turns + current turn partial)."""
        with self._lock:
            current_partial = self._current_turn.total_tokens if self._current_turn else 0
            return self._used_tokens + current_partial

    @property
    def remaining_tokens(self) -> int:
        """Tokens remaining in the session budget."""
        return max(0, self.session_budget - self.used_tokens)

    @property
    def pressure(self) -> float:
        """Current budget pressure (0.0 to 1.0)."""
        if self.session_budget <= 0:
            return 1.0
        return min(1.0, self.used_tokens / self.session_budget)

    @property
    def pressure_zone(self) -> PressureZone:
        """Current pressure zone."""
        p = self.pressure
        if p >= 1.0:
            return PressureZone.EXCEEDED
        if p >= PRESSURE_RED:
            return PressureZone.RED
        if p >= PRESSURE_ORANGE:
            return PressureZone.ORANGE
        if p >= PRESSURE_YELLOW:
            return PressureZone.YELLOW
        return PressureZone.GREEN

    def get_snapshot(self) -> BudgetSnapshot:
        """Return a point-in-time snapshot of budget state."""
        with self._lock:
            return BudgetSnapshot(
                session_budget=self.session_budget,
                used_tokens=self.used_tokens,
                remaining_tokens=self.remaining_tokens,
                pressure=self.pressure,
                pressure_zone=self.pressure_zone,
                turn_count=len(self._turns),
                avg_tokens_per_turn=(
                    self._used_tokens / len(self._turns) if self._turns else 0.0
                ),
            )

    def get_turn_history(self) -> list[TurnRecord]:
        """Return completed turn records."""
        with self._lock:
            return list(self._turns)

    def estimate_turns_remaining(self) -> float:
        """Estimate how many turns can fit in the remaining budget.

        Uses the average token consumption per turn.
        """
        with self._lock:
            if not self._turns:
                return float("inf")
            avg = self._used_tokens / len(self._turns)
            if avg <= 0:
                return float("inf")
            return self.remaining_tokens / avg

    def suggest_compression(self) -> bool:
        """Return True if the agent should proactively compress context."""
        return self.pressure_zone in (
            PressureZone.ORANGE,
            PressureZone.RED,
            PressureZone.EXCEEDED,
        )

    def reset(self) -> None:
        """Reset all tracking state."""
        with self._lock:
            self._used_tokens = 0
            self._turns.clear()
            self._current_turn = None

    # -- Internals -----------------------------------------------------------

    @staticmethod
    def _reduction_factor(zone: PressureZone) -> float:
        """Return the budget reduction factor for a pressure zone.

        1.0 = full budget, 0.5 = half budget, etc.
        """
        return {
            PressureZone.GREEN: 1.0,
            PressureZone.YELLOW: 0.8,
            PressureZone.ORANGE: 0.5,
            PressureZone.RED: 0.25,
            PressureZone.EXCEEDED: 0.05,
        }[zone]
