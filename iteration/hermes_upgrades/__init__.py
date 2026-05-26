"""
Hermes2 Enhanced Module - Architecture upgrades from Claude Code analysis.

Provides:
- ToolOrchestrator: 8-way concurrent tool execution
- ToolResultManager: dedup, truncation, disk persistence
- ContextCompressorV2: 3-level context compression
- MemoryStore: TF-IDF memory system
- PermissionPipeline: layered permission checks
- HookPipeline: post-turn hooks
- AutoDreamer: background memory consolidation
- Coordinator: multi-agent planning
"""

from .hermes2_adapter import Hermes2Config, Hermes2Engine
from .tool_orchestrator import ToolCall, ToolOrchestrator
from .tool_result_manager import ProcessedResult, ToolResultManager
from .permission_pipeline import PermissionLevel, PermissionPipeline, PermissionRule
from .context_compressor_v2 import ContextCompressorV2
from .memory_system import MemoryEntry, MemoryExtractor, MemoryInjector, MemoryStore, MemoryType
from .post_turn_hooks import (
    HookContext,
    HookPipeline,
    HookResult,
    MemoryExtractionHook,
    UsageTrackingHook,
    PromptSuggestionHook,
    ContextHealthHook,
)
from .auto_dream import AutoDreamer, DreamReport, DreamTrigger, SessionSummary
from .coordinator import Coordinator
from .token_utils import extract_text_from_content

__all__ = [
    "Hermes2Engine",
    "Hermes2Config",
    "ToolCall",
    "ToolOrchestrator",
    "ProcessedResult",
    "ToolResultManager",
    "PermissionLevel",
    "PermissionPipeline",
    "PermissionRule",
    "ContextCompressorV2",
    "MemoryEntry",
    "MemoryExtractor",
    "MemoryInjector",
    "MemoryStore",
    "MemoryType",
    "HookContext",
    "HookPipeline",
    "HookResult",
    "MemoryExtractionHook",
    "UsageTrackingHook",
    "PromptSuggestionHook",
    "ContextHealthHook",
    "AutoDreamer",
    "DreamReport",
    "DreamTrigger",
    "SessionSummary",
    "Coordinator",
    "extract_text_from_content",
]

__version__ = "2.0.0"
