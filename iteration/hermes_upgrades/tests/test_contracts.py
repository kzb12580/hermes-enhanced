"""Cross-module contract tests for hermes_upgrades.

Verifies that the data contracts between modules are satisfied:
  1. ToolOrchestrator output → ToolResultManager input
  2. PermissionPipeline output → ToolOrchestrator input
  3. MemoryExtractor output → MemoryStore input
  4. ContextCompressorV2 output → message list format
  5. HookPipeline HookContext matches what Hermes2Engine provides
  6. AutoDreamer TranscriptAnalyzer handles all message formats
  7. Coordinator TaskSpec has all fields that ResultAggregator expects
"""

from __future__ import annotations

import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone
from typing import Any

# Ensure the parent of hermes_upgrades is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from hermes_upgrades.tool_orchestrator import (
    BatchResult,
    ToolCall,
    ToolOrchestrator,
)
from hermes_upgrades.tool_result_manager import (
    ProcessedResult,
    ToolResultManager,
)
from hermes_upgrades.permission_pipeline import (
    PermissionDecision,
    PermissionLevel,
    PermissionPipeline,
)
from hermes_upgrades.memory_system import (
    MemoryEntry,
    MemoryExtractor,
    MemoryStore,
    MemoryType,
)
from hermes_upgrades.context_compressor_v2 import (
    CompressedMessages,
    ContextCompressorV2,
    FullLevel,
)
from hermes_upgrades.post_turn_hooks import (
    HookContext,
    HookPipeline,
    HookResult,
    MemoryExtractionHook,
    UsageTrackingHook,
    PromptSuggestionHook,
    ContextHealthHook,
)
from hermes_upgrades.auto_dream import (
    SessionSummary,
    TranscriptAnalyzer,
)
from hermes_upgrades.coordinator import (
    AggregatedResult,
    ResultAggregator,
    TaskSpec,
    TaskStatus,
)
from hermes_upgrades.hermes2_adapter import Hermes2Engine, Hermes2Config


# ============================================================================
# Contract 1: ToolOrchestrator output is compatible with ToolResultManager input
# ============================================================================


class TestContract_ToolOrchestrator_To_ToolResultManager:
    """ToolOrchestrator.execute() returns dict[str, BatchResult].

    ToolResultManager.process() expects (tool_name: str, content: str).
    The contract: BatchResult.result (Any) must be convertible to str
    and processable by ToolResultManager.process().
    """

    def test_batch_result_content_is_stringifiable(self):
        """Every BatchResult.result must be convertible to str for ToolResultManager."""
        orchestrator = ToolOrchestrator()
        tc = ToolCall(name="read_file", args={"path": "/tmp/test.txt"})
        batches = orchestrator.partition([tc])

        results = orchestrator.execute(batches, lambda tc: "file content here")
        br = results[tc.id]
        assert isinstance(br, BatchResult)
        assert br.error is None
        content = str(br.result)
        assert isinstance(content, str)

    def test_batch_result_to_process_result_pipeline(self):
        """Full pipeline: orchestrator output -> result manager input."""
        orchestrator = ToolOrchestrator()
        manager = ToolResultManager()

        tc = ToolCall(name="read_file", args={"path": "/tmp/test.txt"})
        batches = orchestrator.partition([tc])

        raw_content = "Hello, world! This is a test file content."
        results = orchestrator.execute(batches, lambda tc: raw_content)
        br = results[tc.id]

        processed = manager.process(
            tool_name=tc.name,
            content=str(br.result),
        )
        assert isinstance(processed, ProcessedResult)
        assert isinstance(processed.content, str)
        assert processed.token_count >= 0
        assert isinstance(processed.hash, str)
        assert len(processed.hash) == 64  # SHA-256 hex

    def test_error_batch_result_still_compatible(self):
        """Even errored BatchResults have error fields that are strings."""
        orchestrator = ToolOrchestrator()
        tc = ToolCall(name="terminal", args={"command": "bad_cmd"})
        batches = orchestrator.partition([tc])

        def failing_executor(tc):
            raise RuntimeError("command failed")

        results = orchestrator.execute(batches, failing_executor)
        br = results[tc.id]
        assert br.error is not None
        assert isinstance(br.error, str)
        # Error path: the error string can be fed to result manager
        mgr = ToolResultManager()
        processed = mgr.process(tool_name="terminal", content=br.error)
        assert isinstance(processed, ProcessedResult)

    def test_multiple_results_all_compatible(self):
        """Multiple orchestrator results are all processable."""
        orchestrator = ToolOrchestrator()
        manager = ToolResultManager()

        calls = [
            ToolCall(name="read_file", args={"path": "/tmp/a.txt"}),
            ToolCall(name="search_files", args={"pattern": "*.py"}),
        ]
        batches = orchestrator.partition(calls)

        def executor(tc):
            return f"output for {tc.name}"

        results = orchestrator.execute(batches, executor)

        for tc in calls:
            br = results[tc.id]
            processed = manager.process(tool_name=tc.name, content=str(br.result))
            assert isinstance(processed, ProcessedResult)
            assert processed.token_count >= 0


# ============================================================================
# Contract 2: PermissionPipeline output is compatible with ToolOrchestrator input
# ============================================================================


class TestContract_PermissionPipeline_To_ToolOrchestrator:
    """PermissionPipeline.check() returns PermissionDecision.

    The engine uses PermissionDecision.allowed to gate ToolCall creation.
    """

    def test_permission_decision_has_allowed_field(self):
        """PermissionDecision must have a boolean `allowed` attribute."""
        pipeline = PermissionPipeline()
        decision = pipeline.check("read_file", {"path": "/tmp/test"})
        assert isinstance(decision, PermissionDecision)
        assert isinstance(decision.allowed, bool)

    def test_auto_approved_tools_pass_through(self):
        """Auto-approved tools should have allowed=True and flow to orchestrator."""
        pipeline = PermissionPipeline()
        auto_tools = ["read_file", "search_files", "web_search", "web_extract"]

        for tool_name in auto_tools:
            decision = pipeline.check(tool_name, {})
            assert decision.allowed is True, f"{tool_name} should be auto-approved"

    def test_full_pipeline_permission_to_orchestrator(self):
        """End-to-end: permission filtering -> orchestrator partitioning."""
        pipeline = PermissionPipeline()
        orchestrator = ToolOrchestrator()

        tool_calls_raw = [
            {"name": "read_file", "args": {"path": "/tmp/a.txt"}},
            {"name": "search_files", "args": {"pattern": "*.py"}},
        ]

        allowed_calls = []
        for tc in tool_calls_raw:
            decision = pipeline.check(tc["name"], tc.get("args", {}))
            if decision.allowed:
                allowed_calls.append(
                    ToolCall(name=tc["name"], args=tc.get("args", {}))
                )

        assert len(allowed_calls) == 2
        batches = orchestrator.partition(allowed_calls)
        assert len(batches) >= 1

    def test_prompt_required_tools_are_not_allowed_without_approval(self):
        """PROMPT tools have allowed=False and needs_prompt=True."""
        pipeline = PermissionPipeline()
        decision = pipeline.check("write_file", {"path": "/tmp/test.txt"})
        assert decision.allowed is False
        assert decision.needs_prompt is True

    def test_decision_level_is_valid_enum(self):
        """PermissionDecision.level must be a valid PermissionLevel."""
        pipeline = PermissionPipeline()
        for tool_name in ["read_file", "write_file", "unknown_tool"]:
            decision = pipeline.check(tool_name, {})
            assert isinstance(decision.level, PermissionLevel)
            assert decision.level in (
                PermissionLevel.AUTO,
                PermissionLevel.PROMPT,
                PermissionLevel.DENY,
            )

    def test_decision_to_orchestrator_field_contract(self):
        """PermissionDecision fields used by Hermes2Engine are present."""
        pipeline = PermissionPipeline()
        decision = pipeline.check("read_file", {})
        assert hasattr(decision, "allowed")
        assert callable(getattr(decision, "__init__", None))


# ============================================================================
# Contract 3: MemoryExtractor output is compatible with MemoryStore input
# ============================================================================


class TestContract_MemoryExtractor_To_MemoryStore:
    """MemoryExtractor.extract_from_conversation() returns list[MemoryEntry].

    MemoryStore.add() expects MemoryEntry.
    """

    def test_extractor_produces_memory_entry_objects(self):
        """Extractor output must be MemoryEntry instances."""
        extractor = MemoryExtractor()
        messages = [
            {"role": "user", "content": "I prefer dark mode for all my editors"},
            {"role": "assistant", "content": "I'll remember that preference."},
        ]
        entries = extractor.extract_from_conversation(messages)
        assert len(entries) >= 1
        for entry in entries:
            assert isinstance(entry, MemoryEntry)
            assert isinstance(entry.type, MemoryType)
            assert isinstance(entry.content, str)
            assert isinstance(entry.tags, list)

    def test_extractor_output_addable_to_store(self):
        """Extractor output must be directly compatible with MemoryStore.add()."""
        extractor = MemoryExtractor()
        store = MemoryStore(max_entries=100)

        messages = [
            {"role": "user", "content": "Remember that I prefer Python over JavaScript"},
            {"role": "assistant", "content": "Noted!"},
        ]
        entries = extractor.extract_from_conversation(messages)

        for entry in entries:
            entry_id = store.add(entry)
            assert isinstance(entry_id, str)
            assert len(entry_id) > 0

        assert len(store.entries) == len(entries)

    def test_procedural_memory_entry_contract(self):
        """Procedural memories from extractor must have required fields for store."""
        extractor = MemoryExtractor()
        store = MemoryStore(max_entries=100)

        messages = [
            {"role": "user", "content": "The error was fixed by running pip install --upgrade"},
        ]
        entries = extractor.extract_from_conversation(messages)
        assert len(entries) >= 1

        for entry in entries:
            assert hasattr(entry, "id")
            assert hasattr(entry, "type")
            assert hasattr(entry, "content")
            assert hasattr(entry, "tags")
            assert hasattr(entry, "created_at")
            assert hasattr(entry, "relevance_score")
            store.add(entry)

    def test_list_content_extraction_compatibility(self):
        """Extractor handles OpenAI-style list content and produces store-compatible entries."""
        extractor = MemoryExtractor()
        store = MemoryStore(max_entries=100)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "I prefer using pytest for testing"},
                ],
            },
        ]
        entries = extractor.extract_from_conversation(messages)
        for entry in entries:
            assert isinstance(entry, MemoryEntry)
            store.add(entry)

    def test_memory_entry_serialization_roundtrip(self):
        """MemoryEntry to_dict/from_dict preserves store compatibility."""
        extractor = MemoryExtractor()
        messages = [
            {"role": "user", "content": "I prefer using TypeScript"},
        ]
        entries = extractor.extract_from_conversation(messages)
        assert len(entries) >= 1

        store = MemoryStore(max_entries=100)
        for entry in entries:
            d = entry.to_dict()
            restored = MemoryEntry.from_dict(d)
            store.add(restored)
            retrieved = store.get(restored.id)
            assert retrieved is not None
            assert retrieved.content == entry.content


# ============================================================================
# Contract 4: ContextCompressorV2 output is compatible with message list format
# ============================================================================


class TestContract_ContextCompressorV2_MessageFormat:
    """ContextCompressorV2.compress() returns CompressedMessages.

    CompressedMessages.messages must be a list[dict] where each dict
    has at least 'role' and 'content' keys (standard message format).
    """

    def _make_messages(self, n: int = 20) -> list[dict]:
        """Create a list of standard message dicts."""
        msgs = [{"role": "system", "content": "You are a helpful assistant."}]
        for i in range(n):
            msgs.append({"role": "user", "content": f"Question {i}: " + "word " * 50})
            msgs.append({"role": "assistant", "content": f"Answer {i}: " + "word " * 100})
            msgs.append({
                "role": "tool",
                "content": f"Tool output {i}: " + "data " * 200,
                "name": "terminal",
            })
        return msgs

    def test_compressed_messages_is_list_of_dicts(self):
        """CompressedMessages.messages must be list[dict]."""
        compressor = ContextCompressorV2(model_token_limit=5000, profile="aggressive")
        messages = self._make_messages(30)
        result = compressor.compress(messages, level="micro")
        assert isinstance(result, CompressedMessages)
        assert isinstance(result.messages, list)
        for msg in result.messages:
            assert isinstance(msg, dict)

    def test_compressed_messages_have_required_keys(self):
        """Each compressed message dict must have 'role' and 'content'."""
        compressor = ContextCompressorV2(model_token_limit=5000, profile="aggressive")
        messages = self._make_messages(30)
        result = compressor.compress(messages, level="reactive")

        for msg in result.messages:
            assert "role" in msg, f"Missing 'role' key in message: {msg}"
            assert "content" in msg, f"Missing 'content' key in message: {msg}"
            assert isinstance(msg["role"], str)
            assert isinstance(msg["content"], (str, list))

    def test_compressed_output_passes_token_estimation(self):
        """Compressed messages should have valid token estimates."""
        compressor = ContextCompressorV2(model_token_limit=10000, profile="balanced")
        messages = self._make_messages(20)
        result = compressor.compress(messages, level="reactive")

        assert result.compressed_tokens >= 0
        assert result.original_tokens >= result.compressed_tokens
        assert 0.0 <= result.ratio <= 1.0

    def test_full_level_preserves_message_structure(self):
        """Full-level compression preserves system message and recent context."""
        messages = self._make_messages(20)
        summary = "This is a test summary of the conversation."
        result = FullLevel.apply_summary(messages, summary)

        assert isinstance(result, list)
        for msg in result:
            assert isinstance(msg, dict)
            assert "role" in msg
            assert "content" in msg

    def test_microcompact_preserves_all_roles(self):
        """Microcompact preserves all message roles."""
        compressor = ContextCompressorV2(model_token_limit=5000, profile="aggressive")
        messages = self._make_messages(20)
        result = compressor.compress(messages, level="micro")

        original_roles = [m.get("role") for m in messages]
        compressed_roles = [m.get("role") for m in result.messages]
        assert compressed_roles == original_roles


# ============================================================================
# Contract 5: HookPipeline HookContext matches what Hermes2Engine provides
# ============================================================================


class TestContract_HookContext_Hermes2Engine:
    """Hermes2Engine.process_turn() creates HookContext with:
    - messages, tool_calls, tool_results, turn_number

    HookContext must accept exactly these fields.
    The hooks must be able to process the context without errors.
    """

    def test_hook_context_fields_match_engine_creation(self):
        """HookContext must accept the same fields Hermes2Engine passes."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tool_calls = [
            {"name": "read_file", "args": {"path": "/tmp/test"}},
        ]
        tool_results = [
            {"content": "file content here"},
        ]

        ctx = HookContext(
            messages=messages,
            tool_calls=tool_calls,
            tool_results=tool_results,
            turn_number=1,
        )

        assert ctx.messages == messages
        assert ctx.tool_calls == tool_calls
        assert ctx.tool_results == tool_results
        assert ctx.turn_number == 1

    def test_hook_context_default_values(self):
        """HookContext must have safe defaults for optional fields."""
        ctx = HookContext()
        assert ctx.messages == []
        assert ctx.user_message == ""
        assert ctx.assistant_message == ""
        assert ctx.tool_calls == []
        assert ctx.tool_results == []
        assert ctx.session_id == ""
        assert ctx.turn_number == 0

    def test_hooks_process_engine_context_without_error(self):
        """All built-in hooks must handle the context format Hermes2Engine provides."""
        ctx = HookContext(
            messages=[
                {"role": "user", "content": "I prefer dark mode"},
                {"role": "assistant", "content": "Noted!"},
            ],
            user_message="I prefer dark mode",
            assistant_message="Noted!",
            tool_calls=[{"name": "read_file", "args": {"path": "/tmp/test"}}],
            tool_results=[{"content": "some content"}],
            turn_number=1,
        )

        hooks = [
            MemoryExtractionHook(),
            UsageTrackingHook(),
            PromptSuggestionHook(),
            ContextHealthHook(),
        ]

        for hook in hooks:
            result = asyncio.run(hook.execute(ctx))
            assert isinstance(result, HookResult)
            assert isinstance(result.hook_name, str)
            assert isinstance(result.success, bool)
            assert isinstance(result.data, dict)
            assert isinstance(result.elapsed_ms, float)

    def test_engine_hook_result_serialization_format(self):
        """HookResults must be serializable to the dict format Hermes2Engine uses."""
        ctx = HookContext(
            messages=[{"role": "user", "content": "test"}],
            tool_calls=[],
            tool_results=[],
            turn_number=1,
        )

        hook = UsageTrackingHook()
        result = asyncio.run(hook.execute(ctx))

        serialized = {
            "hook_name": result.hook_name,
            "success": result.success,
            "data": result.data,
            "elapsed_ms": result.elapsed_ms,
            "error": result.error,
        }
        assert isinstance(serialized, dict)
        assert "hook_name" in serialized
        assert "success" in serialized
        assert "data" in serialized


# ============================================================================
# Contract 6: TranscriptAnalyzer handles all message formats the system produces
# ============================================================================


class TestContract_TranscriptAnalyzer_MessageFormats:
    """The system produces messages in various formats.

    TranscriptAnalyzer handles string content. List content (OpenAI format)
    is handled by MemoryExtractor but TranscriptAnalyzer does not currently
    coerce list content — these tests verify the known working formats.
    """

    def setup_method(self):
        self.analyzer = TranscriptAnalyzer()

    def test_standard_user_message(self):
        """Standard user messages are parsed correctly."""
        messages = [{"role": "user", "content": "I prefer using vim for editing"}]
        summary = self.analyzer.analyze(messages)
        assert isinstance(summary, SessionSummary)
        assert len(summary.user_preferences) >= 1

    def test_tool_role_messages(self):
        """Messages with role='tool' are detected for tool usage tracking."""
        messages = [
            {"role": "tool", "content": "file content", "name": "read_file"},
            {"role": "tool", "content": "search results", "name": "search_files"},
        ]
        summary = self.analyzer.analyze(messages)
        assert "read_file" in summary.tools_used
        assert "search_files" in summary.tools_used

    def test_tool_call_type_messages(self):
        """Messages with type='tool_call' are detected for tool usage tracking."""
        messages = [
            {"type": "tool_call", "tool": "terminal", "content": "ls -la"},
        ]
        summary = self.analyzer.analyze(messages)
        assert "terminal" in summary.tools_used

    def test_multipart_content_messages_handled(self):
        """TranscriptAnalyzer handles OpenAI-style list content (fixed).

        Previously crashed with TypeError. Now extracts text from
        multipart content dicts before processing.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "I prefer Python for scripting"},
                ],
            },
        ]
        summary = self.analyzer.analyze(messages)
        assert isinstance(summary, SessionSummary)
        # Should extract the preference from the text part
        assert any("python" in p.lower() for p in summary.user_preferences)

    def test_timestamp_integer_format(self):
        """Integer timestamps are converted and used for duration calculation."""
        messages = [
            {"role": "user", "content": "Hello", "timestamp": 1000000},
            {"role": "assistant", "content": "Hi", "timestamp": 1000600},
        ]
        summary = self.analyzer.analyze(messages)
        assert summary.duration_minutes > 0

    def test_timestamp_datetime_format(self):
        """datetime timestamps are handled for duration calculation."""
        now = datetime.now(timezone.utc)
        messages = [
            {"role": "user", "content": "Hello", "timestamp": now},
            {"role": "assistant", "content": "Hi", "timestamp": now},
        ]
        summary = self.analyzer.analyze(messages)
        assert isinstance(summary.duration_minutes, float)

    def test_empty_content_messages(self):
        """Empty string content is handled gracefully."""
        messages = [
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "Hello"},
        ]
        summary = self.analyzer.analyze(messages)
        assert isinstance(summary, SessionSummary)

    def test_none_content_messages(self):
        """None content is handled gracefully (skipped via `if not content`)."""
        messages = [
            {"role": "assistant", "content": None},
            {"role": "user", "content": "decided to use pytest for testing"},
        ]
        summary = self.analyzer.analyze(messages)
        assert isinstance(summary, SessionSummary)

    def test_error_fixed_extraction(self):
        """Error-fix patterns are extracted from messages."""
        messages = [
            {"role": "user", "content": "The error was fixed by installing the package"},
        ]
        summary = self.analyzer.analyze(messages)
        assert len(summary.errors_fixed) >= 1

    def test_decision_extraction(self):
        """Decision patterns are extracted from messages."""
        messages = [
            {"role": "user", "content": "We decided to use microservices architecture"},
        ]
        summary = self.analyzer.analyze(messages)
        assert len(summary.key_decisions) >= 1

    def test_topic_extraction(self):
        """Topics are extracted from user messages."""
        messages = [
            {"role": "user", "content": "Let's discuss the database migration strategy"},
            {"role": "user", "content": "The database schema needs to be updated"},
        ]
        summary = self.analyzer.analyze(messages)
        assert isinstance(summary.topics, list)

    def test_mixed_format_string_content_messages(self):
        """A realistic mix of message formats (string content only) works together."""
        now = datetime.now(timezone.utc)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "I prefer dark mode for all editors", "timestamp": now},
            {"role": "assistant", "content": "Noted! I'll remember that.", "timestamp": now},
            {"role": "tool", "content": "file content here", "name": "read_file"},
            {"type": "tool_call", "tool": "terminal", "content": "npm install"},
            {"role": "user", "content": "The error was fixed by updating deps"},
            {"role": "assistant", "content": None},
            {"role": "user", "content": ""},
        ]
        summary = self.analyzer.analyze(messages)
        assert isinstance(summary, SessionSummary)
        assert isinstance(summary.tools_used, dict)
        assert isinstance(summary.key_decisions, list)
        assert isinstance(summary.errors_fixed, list)
        assert isinstance(summary.user_preferences, list)
        assert isinstance(summary.topics, list)


# ============================================================================
# Contract 7: Coordinator TaskSpec has all fields that ResultAggregator expects
# ============================================================================


class TestContract_TaskSpec_ResultAggregator:
    """ResultAggregator.aggregate() reads these fields from TaskSpec:
    - id, description, status, result, assigned_to
    """

    def test_task_spec_has_all_required_fields(self):
        """TaskSpec must have all fields that ResultAggregator accesses."""
        task = TaskSpec(description="Test task")
        assert hasattr(task, "id")
        assert hasattr(task, "description")
        assert hasattr(task, "status")
        assert hasattr(task, "result")
        assert hasattr(task, "assigned_to")

    def test_task_spec_field_types(self):
        """TaskSpec fields must have the correct types for aggregation."""
        task = TaskSpec(description="Test task")
        assert isinstance(task.id, str)
        assert isinstance(task.description, str)
        assert isinstance(task.status, TaskStatus)
        assert task.result is None or isinstance(task.result, dict)
        assert task.assigned_to is None or isinstance(task.assigned_to, str)

    def test_result_aggregator_accepts_task_spec_list(self):
        """ResultAggregator.aggregate() must accept list[TaskSpec] and return AggregatedResult."""
        aggregator = ResultAggregator()

        tasks = [
            TaskSpec(
                description="Task 1",
                status=TaskStatus.COMPLETED,
                result={"output": "done"},
                assigned_to="agent-1",
            ),
            TaskSpec(
                description="Task 2",
                status=TaskStatus.FAILED,
                result={"error": "failed"},
                assigned_to="agent-2",
            ),
        ]

        result = aggregator.aggregate(tasks)
        assert isinstance(result, AggregatedResult)
        assert isinstance(result.summary, str)
        assert isinstance(result.details, list)
        assert isinstance(result.all_completed, bool)
        assert isinstance(result.failed_tasks, list)

    def test_result_aggregator_detail_dict_fields(self):
        """Each detail dict must have the expected keys from TaskSpec."""
        aggregator = ResultAggregator()

        task = TaskSpec(
            description="Test task",
            status=TaskStatus.COMPLETED,
            result={"output": "success"},
            assigned_to="agent-1",
        )
        result = aggregator.aggregate([task])

        assert len(result.details) == 1
        detail = result.details[0]
        assert "task_id" in detail
        assert "description" in detail
        assert "status" in detail
        assert "result" in detail
        assert "assigned_to" in detail
        assert detail["task_id"] == task.id
        assert detail["description"] == task.description
        assert detail["status"] == task.status.value
        assert detail["result"] == task.result
        assert detail["assigned_to"] == task.assigned_to

    def test_all_completed_when_all_succeed(self):
        """all_completed is True only when all tasks are COMPLETED."""
        aggregator = ResultAggregator()
        tasks = [
            TaskSpec(description="A", status=TaskStatus.COMPLETED, result={}),
            TaskSpec(description="B", status=TaskStatus.COMPLETED, result={}),
        ]
        result = aggregator.aggregate(tasks)
        assert result.all_completed is True
        assert result.failed_tasks == []

    def test_failed_tasks_collected(self):
        """failed_tasks must contain IDs of all FAILED tasks."""
        aggregator = ResultAggregator()
        t1 = TaskSpec(description="A", status=TaskStatus.COMPLETED, result={})
        t2 = TaskSpec(description="B", status=TaskStatus.FAILED, result={"error": "x"})
        t3 = TaskSpec(description="C", status=TaskStatus.FAILED, result={"error": "y"})

        result = aggregator.aggregate([t1, t2, t3])
        assert result.all_completed is False
        assert t2.id in result.failed_tasks
        assert t3.id in result.failed_tasks
        assert t1.id not in result.failed_tasks

    def test_empty_task_list(self):
        """Aggregator handles empty task list gracefully."""
        aggregator = ResultAggregator()
        result = aggregator.aggregate([])
        assert isinstance(result, AggregatedResult)
        assert result.all_completed is True
        assert result.details == []
        assert result.failed_tasks == []


# ============================================================================
# Integration contract: Hermes2Engine end-to-end data flow
# ============================================================================


class TestContract_Hermes2Engine_Integration:
    """Verify the full Hermes2Engine pipeline maintains data contracts."""

    def test_engine_process_tool_calls_contract(self):
        """process_tool_calls must return dict with expected structure."""
        engine = Hermes2Engine()

        def mock_executor(tc: ToolCall) -> str:
            return f"result for {tc.name}"

        tool_calls = [
            {"name": "read_file", "args": {"path": "/tmp/test.txt"}},
        ]
        results = engine.process_tool_calls(tool_calls, mock_executor)

        assert isinstance(results, dict)
        for tool_id, result in results["processed"].items():
            assert isinstance(tool_id, str)
            assert isinstance(result, dict)
            if "error" not in result:
                assert "content" in result
                assert "was_truncated" in result
                assert "was_deduped" in result
                assert "token_count" in result

    def test_engine_process_turn_contract(self):
        """process_turn must return dict with expected structure."""
        engine = Hermes2Engine()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = engine.process_turn(
            messages=messages,
            tool_calls=[],
            tool_results=[],
        )

        assert isinstance(result, dict)
        assert "hooks_results" in result
        assert "memories_extracted" in result
        assert "compression_applied" in result
        assert "pressure" in result
        assert "pressure_reason" in result

    def test_engine_get_context_messages_contract(self):
        """get_context_messages must return list[dict] with role/content keys."""
        engine = Hermes2Engine()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = engine.get_context_messages(messages)
        assert isinstance(result, list)
        for msg in result:
            assert isinstance(msg, dict)
            assert "role" in msg
            assert "content" in msg
