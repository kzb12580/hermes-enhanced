"""Multi-Agent Coordinator for Hermes Agent.

Provides planning, scheduling, execution, and review capabilities
for coordinating multiple AI agents on complex objectives.
"""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class AgentRole(Enum):
    """Roles an agent can assume in the coordinator."""
    ORCHESTRATOR = "orchestrator"  # Plans and delegates
    WORKER = "worker"              # Executes tasks
    REVIEWER = "reviewer"          # Reviews results


class TaskStatus(Enum):
    """Lifecycle status of a task."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentProfile:
    """Profile describing an agent's identity and capabilities."""
    role: AgentRole
    name: str
    capabilities: list[str]
    model: str = "default"
    max_tasks: int = 3
    active_tasks: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def can_handle(self, required_capabilities: list[str]) -> bool:
        """Check if this agent covers all required capabilities."""
        return all(cap in self.capabilities for cap in required_capabilities)

    def has_capacity(self) -> bool:
        """Check if this agent can accept more tasks."""
        return self.active_tasks < self.max_tasks

    def assign_task(self) -> None:
        """Increment active task count."""
        with self._lock:
            if not self.has_capacity():
                raise ValueError(f"Agent {self.name} is at max capacity ({self.max_tasks})")
            self.active_tasks += 1

    def release_task(self) -> None:
        """Decrement active task count."""
        with self._lock:
            if self.active_tasks <= 0:
                raise ValueError(f"Agent {self.name} has no active tasks to release")
            self.active_tasks -= 1


@dataclass
class TaskSpec:
    """Specification for a single unit of work."""
    description: str
    required_capabilities: list[str] = field(default_factory=list)
    priority: int = 0  # 0 = highest
    context: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class AggregatedResult:
    """Summary of all task results from a coordinator run."""
    summary: str
    details: list[dict[str, Any]]
    all_completed: bool
    failed_tasks: list[str]


# --- Keyword-to-capability mapping for rule-based decomposition ---

_CAPABILITY_KEYWORDS: dict[str, list[str]] = {
    "code": ["code", "implement", "write", "build", "develop", "refactor", "fix", "debug", "program", "function", "class", "module", "script"],
    "research": ["research", "investigate", "find", "search", "analyze", "study", "explore", "review literature", "look up"],
    "test": ["test", "verify", "validate", "check", "assert", "qa", "quality"],
    "deploy": ["deploy", "release", "publish", "ship", "launch", "provision"],
    "review": ["review", "evaluate", "assess", "audit", "inspect"],
    "design": ["design", "architect", "plan", "draft", "sketch", "specify"],
    "data": ["data", "database", "sql", "query", "dataset", "etl", "pipeline"],
}


def _infer_capabilities(text: str) -> list[str]:
    """Infer required capabilities from text keywords."""
    lower = text.lower()
    caps: list[str] = []
    for cap, keywords in _CAPABILITY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                caps.append(cap)
                break
    return caps if caps else ["code"]  # default to code


def _split_sentences(text: str) -> list[str]:
    """Split objective into sub-task sentences."""
    if not isinstance(text, str):
        return []
    parts = re.split(r'[.;]\s*|\band\s+then\s+|\bthen\s+|\balso\s+', text)
    return [p.strip() for p in parts if p.strip()]


# --- Core classes ---


class TaskDecomposer:
    """Breaks a high-level objective into concrete TaskSpec items."""

    def decompose(self, objective: str, context: dict[str, Any] | None = None) -> list[TaskSpec]:
        """Parse objective into sub-tasks with inferred capabilities.

        Args:
            objective: High-level goal description.
            context: Optional shared context for all resulting tasks.

        Returns:
            Ordered list of TaskSpec items.
        """
        sentences = _split_sentences(objective)
        tasks: list[TaskSpec] = []
        ctx = context or {}

        for i, sentence in enumerate(sentences):
            caps = _infer_capabilities(sentence)
            task = TaskSpec(
                description=sentence,
                required_capabilities=caps,
                priority=i,
                context=dict(ctx),
            )
            # Earlier tasks are dependencies of later tasks (logical ordering)
            if tasks:
                task.dependencies = [tasks[-1].id]
            tasks.append(task)

        return tasks

    @staticmethod
    def estimate_complexity(task: TaskSpec) -> str:
        """Estimate task complexity as low / medium / high.

        Heuristic based on description length and number of required capabilities.
        """
        word_count = len(task.description.split())
        cap_count = len(task.required_capabilities)
        score = word_count + cap_count * 5

        if score < 10:
            return "low"
        elif score < 30:
            return "medium"
        return "high"


class TaskScheduler:
    """Matches tasks to agents based on capability and load."""

    def __init__(self, agents: list[AgentProfile]) -> None:
        self.agents = agents

    def schedule(self, tasks: list[TaskSpec]) -> dict[str, list[str]]:
        """Assign tasks to agents.

        Args:
            tasks: Tasks to schedule (modified in-place: status and assigned_to).

        Returns:
            Mapping of agent_id -> list of assigned task_ids.
        """
        # Sort by priority (lower number = higher priority)
        sorted_tasks = sorted(tasks, key=lambda t: t.priority)
        assignments: dict[str, list[str]] = {a.id: [] for a in self.agents}

        # Build a lookup of task statuses by id for dependency checking
        task_status_map: dict[str, TaskStatus] = {t.id: t.status for t in tasks}

        for task in sorted_tasks:
            if task.status not in (TaskStatus.PENDING,):
                continue

            # Check that all dependencies are COMPLETED
            if task.dependencies:
                deps_met = all(
                    task_status_map.get(dep_id) == TaskStatus.COMPLETED
                    for dep_id in task.dependencies
                )
                if not deps_met:
                    continue

            # Find matching agents sorted by load (fewer active tasks first)
            candidates = [
                a for a in self.agents
                if a.role == AgentRole.WORKER
                and a.can_handle(task.required_capabilities)
                and a.has_capacity()
            ]
            candidates.sort(key=lambda a: a.active_tasks)

            if candidates:
                agent = candidates[0]
                agent.assign_task()
                task.assigned_to = agent.id
                task.status = TaskStatus.ASSIGNED
                assignments[agent.id].append(task.id)

        return assignments


class ResultAggregator:
    """Collects and formats task results."""

    def aggregate(self, results: list[TaskSpec]) -> AggregatedResult:
        """Aggregate completed/failed tasks into a summary.

        Args:
            results: All tasks after execution.

        Returns:
            AggregatedResult with summary and details.
        """
        completed = [t for t in results if t.status == TaskStatus.COMPLETED]
        failed = [t for t in results if t.status == TaskStatus.FAILED]
        all_done = len(failed) == 0 and len(completed) == len(results)

        details: list[dict[str, Any]] = []
        for task in results:
            details.append({
                "task_id": task.id,
                "description": task.description,
                "status": task.status.value,
                "result": task.result,
                "assigned_to": task.assigned_to,
            })

        if all_done:
            summary = f"All {len(completed)} tasks completed successfully."
        else:
            summary = (
                f"{len(completed)}/{len(results)} tasks completed. "
                f"{len(failed)} failed."
            )

        return AggregatedResult(
            summary=summary,
            details=details,
            all_completed=all_done,
            failed_tasks=[t.id for t in failed],
        )


class Coordinator:
    """Top-level orchestrator that plans, assigns, executes, and reviews tasks."""

    def __init__(self, agents: list[AgentProfile] | None = None) -> None:
        self.agents = agents or self._default_agents()
        self.decomposer = TaskDecomposer()
        self.scheduler = TaskScheduler(self.agents)
        self.aggregator = ResultAggregator()
        self._tasks: list[TaskSpec] = []

    @staticmethod
    def _default_agents() -> list[AgentProfile]:
        """Create a minimal default agent pool."""
        return [
            AgentProfile(
                role=AgentRole.ORCHESTRATOR,
                name="orchestrator",
                capabilities=["code", "research", "design", "review"],
            ),
            AgentProfile(
                role=AgentRole.WORKER,
                name="coder",
                capabilities=["code", "test"],
                model="default",
            ),
            AgentProfile(
                role=AgentRole.WORKER,
                name="researcher",
                capabilities=["research", "data", "review"],
                model="default",
            ),
            AgentProfile(
                role=AgentRole.REVIEWER,
                name="reviewer",
                capabilities=["review", "test", "code"],
            ),
        ]

    # ---- Public API ----

    def plan(self, objective: str, context: dict[str, Any] | None = None) -> list[TaskSpec]:
        """Decompose objective into task specs.

        Args:
            objective: High-level goal.
            context: Optional context forwarded to every task.

        Returns:
            List of TaskSpec items.
        """
        tasks = self.decomposer.decompose(objective, context)
        self._tasks = tasks
        return tasks

    def assign(self, tasks: list[TaskSpec]) -> dict[str, list[str]]:
        """Schedule tasks to agents.

        Args:
            tasks: Tasks to assign (must already be decomposed).

        Returns:
            Mapping of agent_id -> task_ids.
        """
        return self.scheduler.schedule(tasks)

    def execute(
        self,
        tasks: list[TaskSpec],
        executor_fn: Callable[[TaskSpec], dict[str, Any]],
    ) -> list[TaskSpec]:
        """Run executor_fn on each assigned task.

        Args:
            tasks: Tasks with status ASSIGNED.
            executor_fn: Callable that takes a TaskSpec and returns a result dict.

        Returns:
            The same tasks with updated status and result fields.
        """
        for task in tasks:
            if task.status != TaskStatus.ASSIGNED:
                continue
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            try:
                task.result = executor_fn(task)
                task.status = TaskStatus.COMPLETED
            except Exception as exc:
                task.result = {"error": str(exc)}
                task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(timezone.utc)

            # Release agent capacity
            if task.assigned_to:
                for agent in self.agents:
                    if agent.id == task.assigned_to:
                        agent.release_task()
                        break

        return tasks

    def review(
        self,
        tasks: list[TaskSpec],
        reviewer_fn: Callable[[TaskSpec], dict[str, Any]],
    ) -> dict[str, Any]:
        """Run reviewer_fn on completed tasks.

        Args:
            tasks: Tasks to review.
            reviewer_fn: Callable taking a TaskSpec and returning review feedback.

        Returns:
            Mapping of task_id -> review feedback.
        """
        reviews: dict[str, Any] = {}
        for task in tasks:
            if task.status == TaskStatus.COMPLETED:
                reviews[task.id] = reviewer_fn(task)
        return reviews

    def run_full_cycle(
        self,
        objective: str,
        executor_fn: Callable[[TaskSpec], dict[str, Any]],
        reviewer_fn: Callable[[TaskSpec], dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> AggregatedResult:
        """Plan -> Assign -> Execute -> (optional Review) -> Aggregate.

        Args:
            objective: High-level goal.
            executor_fn: Task execution function.
            reviewer_fn: Optional review function.
            context: Optional shared context.

        Returns:
            AggregatedResult summarizing the run.
        """
        tasks = self.plan(objective, context)
        # Iterate assign-execute cycles to handle task dependencies
        max_rounds = len(tasks) + 1
        for _ in range(max_rounds):
            self.assign(tasks)
            self.execute(tasks, executor_fn)
            # If all tasks are done or no new tasks were assigned, stop
            if all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED) for t in tasks):
                break
        if reviewer_fn:
            self.review(tasks, reviewer_fn)
        return self.aggregator.aggregate(tasks)

    def get_status(self) -> dict[str, Any]:
        """Return current state of agents and tasks.

        Returns:
            Dict with 'agents' and 'tasks' keys.
        """
        agents_info = [
            {
                "id": a.id,
                "name": a.name,
                "role": a.role.value,
                "active_tasks": a.active_tasks,
                "max_tasks": a.max_tasks,
                "capabilities": a.capabilities,
            }
            for a in self.agents
        ]
        tasks_info = [
            {
                "id": t.id,
                "description": t.description,
                "status": t.status.value,
                "assigned_to": t.assigned_to,
                "priority": t.priority,
            }
            for t in self._tasks
        ]
        total = len(self._tasks)
        completed = sum(1 for t in self._tasks if t.status == TaskStatus.COMPLETED)
        return {
            "agents": agents_info,
            "tasks": tasks_info,
            "progress": {
                "total": total,
                "completed": completed,
                "percent": (completed / total * 100) if total else 0,
            },
        }
