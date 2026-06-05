"""File operation tools — read, write, search, list files."""

from __future__ import annotations

import fnmatch
import glob as globmod
import os
import re
import sys
import tempfile
from pathlib import Path

from .base import BaseTool
from . import register


def _detect_encoding(path: str) -> str:
    """Detect file encoding. Try UTF-8 first, then common encodings."""
    try:
        with open(path, 'rb') as f:
            raw = f.read(8192)
    except Exception:
        return 'utf-8'

    if not raw:
        return 'utf-8'

    # Try UTF-8 first (most common)
    try:
        raw.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    # Try common encodings in order of likelihood
    for enc in ['gbk', 'shift_jis', 'euc-jp', 'big5', 'euc-kr', 'latin-1']:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback: try chardet if available
    try:
        import chardet
        result = chardet.detect(raw)
        if result and result.get('encoding'):
            return result['encoding']
    except ImportError:
        pass

    return 'utf-8'  # final fallback


MAX_READ_LINES = 2000
MAX_WRITE_SIZE = 1_000_000  # 1MB
MAX_SEARCH_RESULTS = 50

# ─── Path sandbox ───

_ALLOWED_ROOTS: list[Path] = [
    Path(os.path.expanduser("~")).resolve(),
    Path.cwd().resolve(),
    Path(tempfile.gettempdir()).resolve(),
]

# On Windows, allow all local drive roots (C:\, D:\, H:\, etc.)
if sys.platform == "win32":
    import string
    for drive_letter in string.ascii_uppercase:
        drive = Path(f"{drive_letter}:\\")
        if drive.exists():
            _ALLOWED_ROOTS.append(drive.resolve())

_BLOCKED_PREFIXES: list[Path] = [
    Path("/etc"), Path("/root/.ssh"), Path("/root/.gnupg"), Path("/root/.aws"),
    Path("/root/.config"), Path("/root/.bash_history"), Path("/root/.zsh_history"),
    Path("/proc"), Path("/sys"), Path("/dev"), Path("/boot"), Path("/run"),
    Path("/var/run"), Path("/var/log"),
    Path("/sbin"), Path("/usr/sbin"),
]

# Windows blocked paths
if sys.platform == "win32":
    _win = os.environ.get("SystemRoot", r"C:\Windows")
    _BLOCKED_PREFIXES.extend([
        Path(_win),
        Path(r"C:\Program Files"),
        Path(r"C:\Program Files (x86)"),
        Path(r"C:\ProgramData"),
    ])


def _resolve_safe_path(path_str: str) -> Path | str:
    """Resolve *path_str* and verify it is inside an allowed directory.

    Returns the resolved ``Path`` on success, or an error string on failure.
    """
    try:
        resolved = Path(path_str).expanduser().resolve()
    except (OSError, ValueError) as exc:
        return f"Access denied: cannot resolve path ({exc})"

    # Check blocked system directories
    for blocked in _BLOCKED_PREFIXES:
        if resolved == blocked or blocked in resolved.parents:
            return f"Access denied: path outside allowed directories ({blocked})"

    # Must be under at least one allowed root
    for root in _ALLOWED_ROOTS:
        if resolved == root or root in resolved.parents:
            return resolved

    return "Access denied: path outside allowed directories"


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a file's content with line numbers. Use offset/limit for large files."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "offset": {"type": "integer", "description": "Line number to start from (1-indexed, default 1)", "default": 1},
            "limit": {"type": "integer", "description": "Max lines to read (default 500)", "default": 500},
        },
        "required": ["path"],
    }

    async def execute(self, path: str, offset: int = 1, limit: int = 500, **kwargs) -> str:
        checked = _resolve_safe_path(path)
        if isinstance(checked, str):
            return checked  # error message
        p = checked

        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"
        if p.stat().st_size > MAX_WRITE_SIZE:
            return f"Error: File too large ({p.stat().st_size} bytes)"

        try:
            enc = _detect_encoding(str(p))
            lines = p.read_text(encoding=enc, errors="replace").splitlines()
            total = len(lines)
            start = max(0, offset - 1)
            end = min(total, start + limit)
            selected = lines[start:end]
            numbered = [f"{i + 1}|{line}" for i, line in enumerate(selected, start=start)]
            header = f"Lines {start+1}-{end} of {total} total"
            return header + "\n" + "\n".join(numbered)
        except Exception as e:
            return f"Error reading file: {e}"


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file. Creates parent directories. Overwrites existing content."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str, **kwargs) -> str:
        if len(content) > MAX_WRITE_SIZE:
            return f"Error: Content too large ({len(content)} chars)"

        checked = _resolve_safe_path(path)
        if isinstance(checked, str):
            return checked  # error message
        p = checked

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Written {len(content)} chars to {path}"
        except Exception as e:
            return f"Error writing file: {e}"


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Search for a regex pattern inside files. Returns matching lines with line numbers."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "Directory or file to search in (default: current dir)", "default": "."},
            "file_glob": {"type": "string", "description": "File glob filter, e.g. '*.py'", "default": ""},
        },
        "required": ["pattern"],
    }

    async def execute(self, pattern: str, path: str = ".", file_glob: str = "", **kwargs) -> str:
        checked = _resolve_safe_path(path)
        if isinstance(checked, str):
            return checked  # error message
        target = checked

        if not target.exists():
            return f"Error: Path not found: {path}"

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Error: Invalid regex: {e}"

        import time
        import gc

        results: list[str] = []
        files_scanned = 0
        dirs_scanned = 0
        MAX_FILES = 500
        MAX_DIRS = 2000
        MAX_DEPTH = 8
        TIMEOUT_SEC = 30
        start_time = time.monotonic()

        _SKIP_DIRS = {'.', '..', 'node_modules', '__pycache__', '.git',
                      'venv', '.venv', '.tox', '.mypy_cache', '.pytest_cache',
                      'dist', 'build', '.next', '.nuxt', 'target',
                      '$Recycle.Bin', 'System Volume Information', 'Recovery',
                      'Windows', 'ProgramData', 'Program Files', 'Program Files (x86)'}

        def _check_limits() -> str | None:
            """Return early-exit message if limits exceeded, else None."""
            if len(results) >= MAX_SEARCH_RESULTS:
                return "\n".join(results) + f"\n... (stopped at {MAX_SEARCH_RESULTS} results, scanned {files_scanned} files, {dirs_scanned} dirs)"
            if files_scanned >= MAX_FILES:
                return "\n".join(results) + f"\n... (reached {MAX_FILES} file limit, {dirs_scanned} dirs scanned)" if results else f"No matches in {MAX_FILES} files scanned ({dirs_scanned} dirs). Try a more specific path."
            if dirs_scanned >= MAX_DIRS:
                return "\n".join(results) + f"\n... (reached {MAX_DIRS} dir limit)" if results else f"No matches in {dirs_scanned} directories scanned. Try a more specific path."
            if time.monotonic() - start_time > TIMEOUT_SEC:
                return "\n".join(results) + f"\n... (timeout after {TIMEOUT_SEC}s, scanned {files_scanned} files)" if results else f"Timeout after {TIMEOUT_SEC}s ({files_scanned} files, {dirs_scanned} dirs). Try a more specific path."
            return None

        def _search_file(fpath: Path) -> bool:
            """Search one file. Returns True if should stop."""
            nonlocal files_scanned, results
            files_scanned += 1
            try:
                if fpath.stat().st_size > 2_000_000:  # skip files > 2MB
                    return False
                enc = _detect_encoding(str(fpath))
                text = fpath.read_text(encoding=enc, errors="replace")
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        results.append(f"{fpath}:{i}: {line.strip()}")
                        if len(results) >= MAX_SEARCH_RESULTS:
                            return True
            except (PermissionError, OSError, UnicodeDecodeError):
                pass
            return False

        if target.is_file():
            _search_file(target)
        else:
            # Process directories incrementally — one at a time, free memory after each
            pending_dirs: list[tuple[Path, int]] = [(target, 0)]

            while pending_dirs:
                current_dir, depth = pending_dirs.pop(0)
                dirs_scanned += 1

                # Check limits every iteration
                limit_msg = _check_limits()
                if limit_msg:
                    return limit_msg

                if depth >= MAX_DEPTH:
                    continue

                try:
                    entries = list(current_dir.iterdir())
                except (PermissionError, OSError):
                    continue

                subdirs = []
                for entry in entries:
                    name = entry.name
                    if name in _SKIP_DIRS or name.startswith('.'):
                        continue

                    if entry.is_dir() and not entry.is_symlink():
                        subdirs.append((entry, depth + 1))
                    elif entry.is_file():
                        if file_glob and not fnmatch.fnmatch(name, file_glob):
                            continue
                        if _search_file(entry):
                            # Early exit — enough results
                            limit_msg = _check_limits()
                            return limit_msg if limit_msg else "\n".join(results)

                # Add subdirs to queue (breadth-first)
                pending_dirs.extend(subdirs)

                # Free memory after processing each directory
                del entries, subdirs
                if dirs_scanned % 100 == 0:
                    gc.collect()

        if not results:
            return f"No matches found. (scanned {files_scanned} files, {dirs_scanned} dirs)"
        return "\n".join(results) + f"\n({files_scanned} files, {dirs_scanned} dirs scanned)"


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files and directories in a path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list (default: current dir)", "default": "."},
            "pattern": {"type": "string", "description": "Glob pattern filter, e.g. '*.py'", "default": ""},
        },
        "required": [],
    }

    async def execute(self, path: str = ".", pattern: str = "", **kwargs) -> str:
        checked = _resolve_safe_path(path)
        if isinstance(checked, str):
            return checked  # error message
        target = checked

        if not target.exists():
            return f"Error: Path not found: {path}"

        try:
            if pattern:
                entries = sorted(globmod.glob(str(target / pattern)))
            else:
                entries = sorted(str(p) for p in target.iterdir())

            if not entries:
                return "Empty directory or no matches."

            lines = []
            for e in entries[:100]:
                p = Path(e)
                kind = "d" if p.is_dir() else "f"
                size = p.stat().st_size if p.is_file() else 0
                lines.append(f"[{kind}] {p.name} ({size} bytes)")

            if len(entries) > 100:
                lines.append(f"... and {len(entries) - 100} more")

            return "\n".join(lines)
        except Exception as e:
            return f"Error listing files: {e}"
