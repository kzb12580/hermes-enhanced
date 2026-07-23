"""Session Manager — manages chat sessions with persistence (thread-safe)."""

import json
import logging
import time
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes-backend.session")

# Persistent storage
_SESSIONS_DIR = Path.home() / ".hermes" / "desktop"
_SESSIONS_FILE = _SESSIONS_DIR / "sessions.json"


class SessionManager:
    """Manages chat sessions with JSON persistence (thread-safe)."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        """Load sessions from disk."""
        if _SESSIONS_FILE.exists():
            try:
                data = json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
                self._sessions = data
                logger.info("Loaded %d sessions from %s", len(self._sessions), _SESSIONS_FILE)
            except Exception as e:
                logger.error("Failed to load sessions: %s", e)
                self._sessions = {}

    def _save(self):
        """Save sessions to disk (atomic write, thread-safe)."""
        try:
            _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            data = json.dumps(self._sessions, indent=2, ensure_ascii=False)
            fd, tmp = tempfile.mkstemp(dir=str(_SESSIONS_DIR), suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(data)
                os.replace(tmp, str(_SESSIONS_FILE))
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as e:
            logger.error("Failed to save sessions: %s", e)

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session by ID (thread-safe)."""
        with self._lock:
            return self._sessions.get(session_id)

    def create_session(self, session_id: str, name: Optional[str] = None) -> dict:
        """Create a new session (thread-safe)."""
        session = {
            "id": session_id,
            "name": name or f"Session {session_id[:8]}",
            "messages": [],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        }
        with self._lock:
            self._sessions[session_id] = session
            self._save()
        return session

    def list_sessions(self) -> list[dict]:
        """List all sessions (thread-safe)."""
        with self._lock:
            return [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "message_count": len(s.get("messages", [])),
                    "created_at": s.get("created_at", ""),
                }
                for s in self._sessions.values()
            ]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session (thread-safe)."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._save()
                return True
            return False

    def add_message(self, session_id: str, message: dict):
        """Add a message to a session (thread-safe)."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["messages"].append(message)
                self._save()
