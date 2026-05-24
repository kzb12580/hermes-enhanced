"""Comprehensive tests for the multi-agent coordinator."""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coordinator import (
    AgentProfile,
    AgentRole,
    AggregatedResult,
    Coordinator,
    ResultAggregator,
    TaskDecomposer,
    TaskScheduler,
    TaskSpec,
    TaskStatus,
    _infer_capabilities,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_worker(name="worker-1", capabilities=None, max_tasks=3, active_tasks=0):
    return AgentProfile(
        role=AgentRole.WORKER,
        name=name,
        capabilities=capabilities or ["code"],
        max_tasks=max_tasks,
        active_tasks=active_tasks,
    )


def make_task(description="do something", caps=None, priority=0, status=TaskStatus.PENDING):
    return TaskSpec(
        description=description,
        required_capabilities=caps or ["code"],
        priority=priority,
        status=status,
    )


# ── AgentRole & AgentProfile ─────────────────────────────────────────────────

class TestAgentRole:
    def test_values(self):
        assert AgentRole.ORCHESTRATOR.value == "orchestrator"
        assert AgentRole.WORKER.value == "worker"
        assert AgentRole.REVIEWER.value == "reviewer"


class TestAgentProfile:
    def test_can_handle_simple(self):
        agent = make_worker(capabilities=["code", "test"])
        assert agent.can_handle(["code"])
        assert agent.can_handle(["code", "test"])
        assert not agent.can_handle(["research"])

    def test_can_handle_empty_requirements(self):
        agent = make_worker()
        assert agent.can_handle([])

    def test_has_capacity(self):
        agent = make_worker(max_tasks=2, active_tasks=1)
        assert agent.has_capacity()
        agent.active_tasks = 2
        assert not agent.has_capacity()

    def test_assign_task_increments(self):
        agent = make_worker(max_tasks=3)
        agent.assign_task()
        assert agent.active_tasks == 1

    def test_assign_task_over_capacity_raises(self):
        agent = make_worker(max_tasks=1, active_tasks=1)
        with pytest.raises(ValueError, match="max capacity"):
            agent.assign_task()

    def test_release_task_decrements(self):
        agent = make_worker(active_tasks=2)
        agent.release_task()
        assert agent.active_tasks == 1

    def test_release_task_at_zero_stays_zero(self):
        agent = make_worker(active_tasks=0)
        agent.release_task()
        assert agent.active_tasks == 0


# ── TaskSpec ──────────────────────────────────────────────────────────────────

class TestTaskSpec:
    def test_defaults(self):
        task = TaskSpec(description="hello")
        assert task.status == TaskStatus.PENDING
        assert task.priority == 0
        assert task.result is None
        assert task.assigned_to is None
        assert task.id  # auto-generated UUID

    def test_unique_ids(self):
        t1 = TaskSpec(description="a")
        t2 = TaskSpec(description="b")
        assert t1.id != t2.id


# ── Capability inference ─────────────────────────────────────────────────────

class TestInferCapabilities:
    def test_code_keywords(self):
        assert "code" in _infer_capabilities("implement the login module")

    def test_research_keywords(self):
        assert "research" in _infer_capabilities("investigate the root cause")

    def test_test_keywords(self):
        assert "test" in _infer_capabilities("verify the output is correct")

    def test_deploy_keywords(self):
        assert "deploy" in _infer_capabilities("deploy to production")

    def test_multiple_capabilities(self):
        caps = _infer_capabilities("implement and test the API")
        assert "code" in caps
        assert "test" in caps

    def test_no_match_defaults_to_code(self):
        caps = _infer_capabilities("make it better")
        assert caps == ["code"]


# ── TaskDecomposer ────────────────────────────────────────────────────────────

class TestTaskDecomposer:
    def test_single_sentence(self):
        d = TaskDecomposer()
        tasks = d.decompose("Implement the login page")
        assert len(tasks) == 1
        assert "code" in tasks[0].required_capabilities

    def test_multiple_sentences_semicolon(self):
        d = TaskDecomposer()
        tasks = d.decompose("Research the API; Implement the client; Test the integration")
        assert len(tasks) == 3
        assert "research" in tasks[0].required_capabilities
        assert "code" in tasks[1].required_capabilities
        assert "test" in tasks[2].required_capabilities

    def test_multiple_sentences_then(self):
        d = TaskDecomposer()
        tasks = d.decompose("Build the model and then deploy the service")
        assert len(tasks) == 2

    def test_dependencies_chain(self):
        d = TaskDecomposer()
        tasks = d.decompose("Step one; Step two; Step three")
        assert tasks[0].dependencies == []
        assert tasks[1].dependencies == [tasks[0].id]
        assert tasks[2].dependencies == [tasks[1].id]

    def test_priority_ordering(self):
        d = TaskDecomposer()
        tasks = d.decompose("First task; Second task; Third task")
        assert tasks[0].priority == 0
        assert tasks[1].priority == 1
        assert tasks[2].priority == 2

    def test_context_propagated(self):
        d = TaskDecomposer()
        tasks = d.decompose("Do stuff", context={"file": "main.py"})
        assert tasks[0].context["file"] == "main.py"

    def test_estimate_complexity_low(self):
        d = TaskDecomposer()
        task = make_task(description="fix bug", caps=["code"])
        assert d.estimate_complexity(task) == "low"

    def test_estimate_complexity_high(self):
        d = TaskDecomposer()
        task = make_task(
            description="implement the full authentication and authorization system with OAuth2 RBAC and comprehensive role-based access control for all endpoints and resources",
            caps=["code", "design", "test"],
        )
        assert d.estimate_complexity(task) == "high"


# ── TaskScheduler ─────────────────────────────────────────────────────────────

class TestTaskScheduler:
    def test_basic_scheduling(self):
        w = make_worker("w1", ["code"])
        scheduler = TaskScheduler([w])
        tasks = [make_task(caps=["code"])]
        assignments = scheduler.schedule(tasks)
        assert tasks[0].assigned_to == w.id
        assert tasks[0].status == TaskStatus.ASSIGNED
        assert w.id in assignments

    def test_capability_matching(self):
        w_code = make_worker("coder", ["code"])
        w_res = make_worker("researcher", ["research"])
        scheduler = TaskScheduler([w_code, w_res])
        t1 = make_task("code task", caps=["code"], priority=0)
        t2 = make_task("research task", caps=["research"], priority=1)
        assignments = scheduler.schedule([t1, t2])
        assert t1.assigned_to == w_code.id
        assert t2.assigned_to == w_res.id

    def test_load_balancing(self):
        w1 = make_worker("w1", ["code"], max_tasks=3, active_tasks=2)
        w2 = make_worker("w2", ["code"], max_tasks=3, active_tasks=0)
        scheduler = TaskScheduler([w1, w2])
        task = make_task(caps=["code"])
        scheduler.schedule([task])
        assert task.assigned_to == w2.id  # less loaded agent

    def test_priority_ordering(self):
        w = make_worker("w1", ["code"], max_tasks=1)
        scheduler = TaskScheduler([w])
        low_pri = make_task("low", caps=["code"], priority=10)
        high_pri = make_task("high", caps=["code"], priority=0)
        scheduler.schedule([high_pri, low_pri])
        # Only one can be assigned (max_tasks=1); high priority wins
        assert high_pri.status == TaskStatus.ASSIGNED
        assert low_pri.status == TaskStatus.PENDING  # unassigned

    def test_no_matching_agent(self):
        w = make_worker("w1", ["code"])
        scheduler = TaskScheduler([w])
        task = make_task(caps=["research"])
        assignments = scheduler.schedule([task])
        assert task.status == TaskStatus.PENDING
        assert task.assigned_to is None

    def test_skip_non_pending_tasks(self):
        w = make_worker("w1", ["code"])
        scheduler = TaskScheduler([w])
        task = make_task(status=TaskStatus.COMPLETED)
        scheduler.schedule([task])
        assert task.assigned_to is None


# ── ResultAggregator ──────────────────────────────────────────────────────────

class TestResultAggregator:
    def test_all_completed(self):
        agg = ResultAggregator()
        t1 = make_task(status=TaskStatus.COMPLETED)
        t1.result = {"output": "ok"}
        t2 = make_task(status=TaskStatus.COMPLETED)
        t2.result = {"output": "ok"}
        result = agg.aggregate([t1, t2])
        assert result.all_completed
        assert len(result.failed_tasks) == 0
        assert "2/2" in result.summary or "All" in result.summary

    def test_some_failed(self):
        agg = ResultAggregator()
        t1 = make_task(status=TaskStatus.COMPLETED)
        t1.result = {"output": "ok"}
        t2 = make_task(status=TaskStatus.FAILED)
        t2.result = {"error": "boom"}
        result = agg.aggregate([t1, t2])
        assert not result.all_completed
        assert t2.id in result.failed_tasks
        assert "1/2" in result.summary

    def test_details_structure(self):
        agg = ResultAggregator()
        t = make_task("my task", status=TaskStatus.COMPLETED)
        t.result = {"data": 42}
        t.assigned_to = "agent-1"
        result = agg.aggregate([t])
        assert len(result.details) == 1
        d = result.details[0]
        assert d["task_id"] == t.id
        assert d["description"] == "my task"
        assert d["status"] == "completed"
        assert d["result"] == {"data": 42}
        assert d["assigned_to"] == "agent-1"


# ── Coordinator ───────────────────────────────────────────────────────────────

class TestCoordinator:
    def test_default_agents(self):
        c = Coordinator()
        assert len(c.agents) >= 3
        roles = {a.role for a in c.agents}
        assert AgentRole.ORCHESTRATOR in roles
        assert AgentRole.WORKER in roles

    def test_plan(self):
        c = Coordinator()
        tasks = c.plan("Research the API; Implement the client")
        assert len(tasks) == 2
        assert "research" in tasks[0].required_capabilities
        assert "code" in tasks[1].required_capabilities

    def test_assign(self):
        c = Coordinator()
        tasks = c.plan("Implement the module")
        assignments = c.assign(tasks)
        assert any(len(v) > 0 for v in assignments.values())

    def test_execute_success(self):
        c = Coordinator()
        tasks = c.plan("Implement feature X")
        c.assign(tasks)
        results = c.execute(tasks, lambda t: {"output": "done"})
        assert all(t.status == TaskStatus.COMPLETED for t in results if t.status != TaskStatus.PENDING)

    def test_execute_failure(self):
        c = Coordinator()
        tasks = c.plan("Build something")
        c.assign(tasks)

        def failing_fn(task):
            raise RuntimeError("boom")

        results = c.execute(tasks, failing_fn)
        failed = [t for t in results if t.status == TaskStatus.FAILED]
        assert len(failed) > 0
        assert failed[0].result is not None
        assert "boom" in failed[0].result["error"]

    def test_review(self):
        c = Coordinator()
        tasks = c.plan("Implement feature")
        c.assign(tasks)
        c.execute(tasks, lambda t: {"output": "ok"})
        reviews = c.review(tasks, lambda t: {"approved": True})
        assert len(reviews) > 0
        assert all(v["approved"] for v in reviews.values())

    def test_run_full_cycle(self):
        c = Coordinator()
        result = c.run_full_cycle(
            "Implement login; Test the login",
            executor_fn=lambda t: {"output": "ok"},
        )
        assert isinstance(result, AggregatedResult)
        assert result.all_completed
        assert len(result.details) == 2

    def test_run_full_cycle_with_reviewer(self):
        c = Coordinator()
        reviews_collected = []
        result = c.run_full_cycle(
            "Research topic; Write report",
            executor_fn=lambda t: {"output": "ok"},
            reviewer_fn=lambda t: reviews_collected.append(t.id) or {"approved": True},
        )
        assert result.all_completed
        assert len(reviews_collected) > 0

    def test_run_full_cycle_with_context(self):
        c = Coordinator()
        result = c.run_full_cycle(
            "Build the API",
            executor_fn=lambda t: {"ctx": t.context.get("project")},
            context={"project": "myapp"},
        )
        assert result.all_completed
        assert result.details[0]["result"]["ctx"] == "myapp"

    def test_get_status(self):
        c = Coordinator()
        c.plan("Task A; Task B")
        status = c.get_status()
        assert "agents" in status
        assert "tasks" in status
        assert "progress" in status
        assert status["progress"]["total"] == 2
        assert status["progress"]["completed"] == 0

    def test_get_status_after_execution(self):
        c = Coordinator()
        c.run_full_cycle("Do the thing", executor_fn=lambda t: {"ok": True})
        status = c.get_status()
        assert status["progress"]["completed"] == status["progress"]["total"]
        assert status["progress"]["percent"] == 100.0

    def test_unassigned_tasks_skipped_in_execute(self):
        c = Coordinator()
        # Create a task that won't match any worker
        tasks = [TaskSpec(description="magic", required_capabilities=["nonexistent"])]
        results = c.execute(tasks, lambda t: {"x": 1})
        # Task should remain PENDING (never assigned, never executed)
        assert results[0].status == TaskStatus.PENDING
