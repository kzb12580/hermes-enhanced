"""Tool Result Summarizer for Hermes Agent.

Provides intelligent, structure-aware summarization of tool results that
preserves the most important information, unlike simple head/tail truncation.

FEATURE GAP FIXED: The existing SmartTruncator just chops head and tail,
losing the middle of the content. For structured outputs (code files, search
results, terminal logs), there are much better summarization strategies that
preserve key information while reducing token count.

Strategies:
- code_file: Extract function/class signatures, imports, docstrings
- terminal: Extract exit code, last N lines, errors/warnings
- search_results: Extract file paths and match counts
- json_data: Extract keys and structure
- generic: Head+tail with intelligent line selection

Usage:
    summarizer = ToolResultSummarizer()
    summary = summarizer.summarize(
        tool_name="read_file",
        content=long_file_content,
        target_tokens=2000,
    )
    # summary.content is a condensed version preserving key info
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

try:
    from .tool_result_manager import TokenEstimator
except ImportError:
    from tool_result_manager import TokenEstimator


# ---------------------------------------------------------------------------
# Summary Strategy
# ---------------------------------------------------------------------------


class SummaryStrategy(Enum):
    """Available summarization strategies."""
    CODE_FILE = auto()      # Extract structure from code
    TERMINAL_OUTPUT = auto() # Extract key lines from terminal output
    SEARCH_RESULTS = auto()  # Extract paths and counts from search
    JSON_DATA = auto()       # Extract structure from JSON
    GENERIC = auto()         # Smart head+tail with line selection


@dataclass
class SummaryResult:
    """Result of a summarization operation."""
    content: str
    strategy: SummaryStrategy
    original_tokens: int
    summarized_tokens: int
    compression_ratio: float
    key_info_preserved: list[str]  # what was kept


# ---------------------------------------------------------------------------
# Code File Summarizer
# ---------------------------------------------------------------------------


class CodeFileSummarizer:
    """Summarize code files by extracting structural elements."""

    # Patterns for Python structural elements
    _PY_IMPORT = re.compile(r"^(?:from\s+\S+\s+)?import\s+.+", re.MULTILINE)
    _PY_CLASS = re.compile(r"^class\s+\w+.*?(?=\n\S|\Z)", re.MULTILINE | re.DOTALL)
    _PY_DEF = re.compile(r"^\s*def\s+\w+\s*\([^)]*\).*?(?=\n\S|\n\s*def|\n\s*class|\Z)", re.MULTILINE | re.DOTALL)
    _PY_DOCSTRING = re.compile(r'^\s*(?:"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', re.MULTILINE)
    _PY_DECORATOR = re.compile(r"^\s*@\w+.*$", re.MULTILINE)

    # Patterns for JS/TS structural elements
    _JS_EXPORT = re.compile(r"^export\s+(?:default\s+)?(?:function|class|const|let|var)\s+\w+.*", re.MULTILINE)
    _JS_FUNCTION = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+\w+\s*\([^)]*\).*", re.MULTILINE)
    _JS_CLASS = re.compile(r"^(?:export\s+)?class\s+\w+.*?\{", re.MULTILINE)

    def summarize_python(self, content: str, target_tokens: int) -> tuple[str, list[str]]:
        """Summarize a Python file by extracting structure."""
        preserved = []

        # Extract imports
        imports = self._PY_IMPORT.findall(content)
        import_text = "\n".join(imports[:20])  # Cap at 20 imports

        # Extract class and function signatures (just the def line + docstring)
        signatures = []
        for match in re.finditer(r"^(class\s+\w+[^\n:]*)", content, re.MULTILINE):
            sig = match.group(1).rstrip(":")
            signatures.append(sig)

        for match in re.finditer(r"^\s*(def\s+\w+\s*\([^)]*\)[^\n:]*)", content, re.MULTILINE):
            sig = match.group(1).rstrip(":")
            signatures.append(sig)

        sig_text = "\n".join(signatures)

        # Try to get the module docstring
        docstring = ""
        ds_match = self._PY_DOCSTRING.match(content)
        if ds_match:
            docstring = ds_match.group(0).strip()[:500]

        # Assemble summary
        parts = []
        if docstring:
            parts.append(docstring)
            preserved.append("module docstring")
        if imports:
            parts.append(f"# --- Imports ({len(imports)} total) ---\n" + import_text)
            preserved.append(f"{len(imports)} import statements")
        if signatures:
            parts.append(f"# --- Signatures ({len(signatures)} definitions) ---\n" + sig_text)
            preserved.append(f"{len(signatures)} class/function signatures")

        # Add a tail excerpt with a few lines
        lines = content.splitlines()
        if len(lines) > 5:
            tail = "\n".join(lines[-5:])
            parts.append(f"# --- Last 5 lines ---\n{tail}")
            preserved.append("tail context")

        summary = "\n\n".join(parts)
        if not summary:
            summary = content[:target_tokens * 4]  # fallback
            preserved.append("head excerpt (fallback)")

        return summary, preserved

    def summarize_js(self, content: str, target_tokens: int) -> tuple[str, list[str]]:
        """Summarize a JavaScript/TypeScript file by extracting structure."""
        preserved = []

        # Extract exports and declarations
        exports = self._JS_EXPORT.findall(content)
        export_text = "\n".join(exports[:20])

        # Extract function signatures
        functions = self._JS_FUNCTION.findall(content)
        func_text = "\n".join(functions[:20])

        # Extract class headers
        classes = self._JS_CLASS.findall(content)
        class_text = "\n".join(classes[:10])

        parts = []
        if exports:
            parts.append(f"// --- Exports ({len(exports)} total) ---\n" + export_text)
            preserved.append(f"{len(exports)} export statements")
        if classes:
            parts.append(f"// --- Classes ({len(classes)}) ---\n" + class_text)
            preserved.append(f"{len(classes)} class declarations")
        if functions:
            parts.append(f"// --- Functions ({len(functions)}) ---\n" + func_text)
            preserved.append(f"{len(functions)} function declarations")

        lines = content.splitlines()
        if len(lines) > 5:
            tail = "\n".join(lines[-5:])
            parts.append(f"// --- Last 5 lines ---\n{tail}")
            preserved.append("tail context")

        summary = "\n\n".join(parts)
        if not summary:
            summary = content[:target_tokens * 4]
            preserved.append("head excerpt (fallback)")

        return summary, preserved


# ---------------------------------------------------------------------------
# Terminal Output Summarizer
# ---------------------------------------------------------------------------


class TerminalSummarizer:
    """Summarize terminal/command output by extracting key information."""

    _ERROR_PATTERNS = [
        re.compile(r"(?:error|Error|ERROR).*", re.I),
        re.compile(r"(?:fatal|Fatal|FATAL).*", re.I),
        re.compile(r"(?:warning|Warning|WARNING).*", re.I),
        re.compile(r"(?:Traceback|Exception).*", re.I),
        re.compile(r"^\s*at\s+", re.MULTILINE),  # stack trace lines
    ]

    _EXIT_CODE_PATTERN = re.compile(r"exit\s*(?:code|status)[:\s]*(\d+)", re.I)

    def summarize(self, content: str, target_tokens: int) -> tuple[str, list[str]]:
        """Summarize terminal output."""
        preserved = []
        lines = content.splitlines()

        if not lines:
            return "", []

        # Early exit: if within token budget, return content as-is
        # before expensive regex processing
        if TokenEstimator.estimate_tokens(content) <= target_tokens:
            return content, ["full output (within budget)"]

        parts = []

        # Extract exit code if present
        exit_match = self._EXIT_CODE_PATTERN.search(content)
        if exit_match:
            parts.append(f"[Exit code: {exit_match.group(1)}]")
            preserved.append("exit code")

        # Extract error/warning lines
        error_lines = []
        for line in lines:
            for pat in self._ERROR_PATTERNS:
                if pat.search(line):
                    error_lines.append(line.strip())
                    break

        if error_lines:
            # Deduplicate and cap at 20
            seen = set()
            unique_errors = []
            for el in error_lines:
                normalized = el.strip()
                if normalized not in seen:
                    seen.add(normalized)
                    unique_errors.append(el)
                if len(unique_errors) >= 20:
                    break

            parts.append("[Errors/Warnings]\n" + "\n".join(unique_errors))
            preserved.append(f"{len(unique_errors)} error/warning lines")

        # Always include the last N lines (most recent output)
        tail_n = min(15, len(lines))
        tail = lines[-tail_n:]
        parts.append(f"[Last {tail_n} lines]\n" + "\n".join(tail))
        preserved.append(f"last {tail_n} lines of output")

        # If very short, just return the whole thing
        summary = "\n\n".join(parts)
        if TokenEstimator.estimate_tokens(content) <= target_tokens:
            return content, ["full output (within budget)"]

        return summary, preserved


# ---------------------------------------------------------------------------
# Search Results Summarizer
# ---------------------------------------------------------------------------


class SearchResultSummarizer:
    """Summarize search results by extracting paths and match info."""

    _FILE_PATH_PATTERN = re.compile(r"(?:^|\s)([\w./-]+\.\w+)(?:\s|:|$)")
    _MATCH_COUNT_PATTERN = re.compile(r"(\d+)\s+(?:match|result|hit|occurrence)", re.I)

    def summarize(self, content: str, target_tokens: int) -> tuple[str, list[str]]:
        """Summarize search results."""
        preserved = []
        lines = content.splitlines()

        if not lines:
            return "", []

        # If short enough, return as-is
        if TokenEstimator.estimate_tokens(content) <= target_tokens:
            return content, ["full results (within budget)"]

        # Extract unique file paths
        paths: list[str] = []
        seen_paths: set[str] = set()
        for line in lines:
            match = self._FILE_PATH_PATTERN.search(line)
            if match:
                path = match.group(1)
                if path not in seen_paths:
                    seen_paths.add(path)
                    paths.append(path)

        # Extract match count if present
        match_count = None
        for line in lines[:5]:  # Check first few lines
            mc = self._MATCH_COUNT_PATTERN.search(line)
            if mc:
                match_count = mc.group(1)
                break

        parts = []
        if match_count:
            parts.append(f"[Total matches: {match_count}]")
            preserved.append("total match count")

        if paths:
            path_list = paths[:50]  # Cap at 50 paths
            parts.append(f"[{len(path_list)} unique files]\n" + "\n".join(path_list))
            preserved.append(f"{len(path_list)} file paths")

        # Include a sample of the actual content
        sample_lines = lines[:10]
        parts.append("[First 10 lines]\n" + "\n".join(sample_lines))
        preserved.append("first 10 lines sample")

        summary = "\n\n".join(parts)
        if not summary:
            summary = content[:target_tokens * 4]
            preserved.append("head excerpt (fallback)")

        return summary, preserved


# ---------------------------------------------------------------------------
# JSON Data Summarizer
# ---------------------------------------------------------------------------


class JsonSummarizer:
    """Summarize JSON data by extracting structure and key information."""

    def summarize(self, content: str, target_tokens: int) -> tuple[str, list[str]]:
        """Summarize JSON data."""
        preserved = []

        # Don't attempt to parse extremely large JSON to avoid OOM
        _MAX_JSON_PARSE_SIZE = 1_000_000  # 1MB
        if len(content) > _MAX_JSON_PARSE_SIZE:
            return content[:target_tokens * 4], ["JSON too large to parse: head excerpt"]

        # Try to parse as JSON
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # Not JSON — fall back to generic
            return content[:target_tokens * 4], ["non-JSON: head excerpt"]

        if isinstance(data, list):
            return self._summarize_list(data, preserved)
        elif isinstance(data, dict):
            return self._summarize_dict(data, preserved)
        else:
            return str(data), ["primitive value"]

    def _summarize_list(self, data: list, preserved: list[str]) -> tuple[str, list[str]]:
        """Summarize a JSON array."""
        parts = [f"[Array with {len(data)} items]"]
        preserved.append(f"array length: {len(data)}")

        if data:
            # Show first 3 items
            sample = data[:3]
            parts.append(f"[First {len(sample)} items]")
            for i, item in enumerate(sample):
                if isinstance(item, dict):
                    keys = list(item.keys())[:10]
                    parts.append(f"  Item {i}: keys={keys}")
                else:
                    parts.append(f"  Item {i}: {str(item)[:200]}")
            preserved.append(f"first {len(sample)} items preview")

        return "\n".join(parts), preserved

    def _summarize_dict(self, data: dict, preserved: list[str]) -> tuple[str, list[str]]:
        """Summarize a JSON object."""
        parts = [f"[Object with {len(data)} keys]"]
        preserved.append(f"object keys: {len(data)}")

        # List all top-level keys
        keys = list(data.keys())
        parts.append(f"[Keys: {', '.join(str(k) for k in keys[:30])}]")
        preserved.append(f"{len(keys)} top-level keys")

        # Show values for first 5 keys
        for key in list(data.keys())[:5]:
            val = data[key]
            if isinstance(val, (dict, list)):
                if isinstance(val, list):
                    parts.append(f"  {key}: [array, {len(val)} items]")
                else:
                    parts.append(f"  {key}: [object, {len(val)} keys]")
            else:
                val_str = str(val)[:200]
                parts.append(f"  {key}: {val_str}")
        preserved.append("first 5 key-value previews")

        return "\n".join(parts), preserved


# ---------------------------------------------------------------------------
# ToolResultSummarizer (main class)
# ---------------------------------------------------------------------------


class ToolResultSummarizer:
    """High-level summarizer that picks the best strategy per tool.

    Parameters
    ----------
    estimator : TokenEstimator | None
        Token estimator instance.
    """

    def __init__(self, estimator: TokenEstimator | None = None) -> None:
        self._estimator = estimator or TokenEstimator()
        self._code_summarizer = CodeFileSummarizer()
        self._terminal_summarizer = TerminalSummarizer()
        self._search_summarizer = SearchResultSummarizer()
        self._json_summarizer = JsonSummarizer()

    def summarize(
        self,
        tool_name: str,
        content: str,
        target_tokens: int,
        file_path: str | None = None,
    ) -> SummaryResult:
        """Summarize a tool result using the best strategy.

        Parameters
        ----------
        tool_name : str
            Name of the tool that produced the result.
        content : str
            Raw tool output.
        target_tokens : int
            Target token count for the summary.
        file_path : str | None
            Original file path (used for strategy selection).

        Returns
        -------
        SummaryResult with condensed content.
        """
        if not content:
            return SummaryResult(
                content="",
                strategy=SummaryStrategy.GENERIC,
                original_tokens=0,
                summarized_tokens=0,
                compression_ratio=1.0,
                key_info_preserved=["empty input"],
            )

        original_tokens = self._estimator.estimate_tokens(content)

        # If already within budget, return as-is
        if original_tokens <= target_tokens:
            return SummaryResult(
                content=content,
                strategy=SummaryStrategy.GENERIC,
                original_tokens=original_tokens,
                summarized_tokens=original_tokens,
                compression_ratio=1.0,
                key_info_preserved=["within budget — no summarization needed"],
            )

        # Select strategy
        strategy = self._select_strategy(tool_name, content, file_path)

        # Apply strategy
        if strategy == SummaryStrategy.CODE_FILE:
            ext = self._get_extension(file_path or "")
            if ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
                summarized, preserved = self._code_summarizer.summarize_js(
                    content, target_tokens
                )
            else:
                summarized, preserved = self._code_summarizer.summarize_python(
                    content, target_tokens
                )
        elif strategy == SummaryStrategy.TERMINAL_OUTPUT:
            summarized, preserved = self._terminal_summarizer.summarize(
                content, target_tokens
            )
        elif strategy == SummaryStrategy.SEARCH_RESULTS:
            summarized, preserved = self._search_summarizer.summarize(
                content, target_tokens
            )
        elif strategy == SummaryStrategy.JSON_DATA:
            summarized, preserved = self._json_summarizer.summarize(
                content, target_tokens
            )
        else:
            # Generic fallback: head + tail
            summarized, preserved = self._generic_summarize(
                content, target_tokens
            )

        summarized_tokens = self._estimator.estimate_tokens(summarized)
        ratio = summarized_tokens / original_tokens if original_tokens > 0 else 1.0

        return SummaryResult(
            content=summarized,
            strategy=strategy,
            original_tokens=original_tokens,
            summarized_tokens=summarized_tokens,
            compression_ratio=ratio,
            key_info_preserved=preserved,
        )

    def _select_strategy(
        self, tool_name: str, content: str, file_path: str | None
    ) -> SummaryStrategy:
        """Select the best summarization strategy."""
        # Check tool name first
        if tool_name == "terminal":
            return SummaryStrategy.TERMINAL_OUTPUT
        if tool_name == "search_files":
            return SummaryStrategy.SEARCH_RESULTS

        # Check file extension
        if file_path:
            ext = self._get_extension(file_path)
            if ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".go", ".rs",
                       ".java", ".c", ".cpp", ".h", ".hpp", ".rb", ".php"):
                return SummaryStrategy.CODE_FILE
            if ext == ".json":
                return SummaryStrategy.JSON_DATA

        # Check content for JSON
        stripped = content.lstrip()
        if stripped.startswith(("{", "[")):
            # Try parsing the full content first (most reliable)
            try:
                json.loads(content)
                return SummaryStrategy.JSON_DATA
            except (json.JSONDecodeError, ValueError):
                pass

        # Check content for code-like patterns
        if re.search(r"^(?:class|def|function|import|export)\s", content, re.MULTILINE):
            return SummaryStrategy.CODE_FILE

        return SummaryStrategy.GENERIC

    def _generic_summarize(
        self, content: str, target_tokens: int
    ) -> tuple[str, list[str]]:
        """Generic head + tail summarization with line awareness."""
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        preserved = []

        if total_lines <= 10:
            return content, ["short content — kept in full"]

        # Calculate how many lines to keep
        chars_budget = target_tokens * 4
        head_chars = int(chars_budget * 0.4)
        tail_chars = int(chars_budget * 0.3)

        # Build head
        head_lines = []
        char_count = 0
        for line in lines:
            if char_count + len(line) > head_chars:
                break
            head_lines.append(line)
            char_count += len(line)

        # Build tail
        tail_lines = []
        char_count = 0
        for line in reversed(lines):
            if char_count + len(line) > tail_chars:
                break
            tail_lines.insert(0, line)
            char_count += len(line)

        removed = total_lines - len(head_lines) - len(tail_lines)
        if removed <= 0:
            # Head and tail overlap or cover everything — keep original
            return content, ["content is short enough, kept in full"]

        marker = f"\n[... {removed} lines omitted ({total_lines} total) ...]\n"

        preserved.append(f"first {len(head_lines)} lines")
        preserved.append(f"last {len(tail_lines)} lines")
        preserved.append(f"{removed} middle lines removed")

        return "".join(head_lines) + marker + "".join(tail_lines), preserved

    @staticmethod
    def _get_extension(path: str) -> str:
        """Get the file extension from a path."""
        if "." in path:
            return "." + path.rsplit(".", 1)[-1].lower()
        return ""
