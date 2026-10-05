"""Conversation memory and session metadata persisted in SQLite."""

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    summarized_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    chunks INTEGER NOT NULL,
    chars INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_session ON documents(session_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MemoryStore:
    def __init__(self, path: Path | str):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall()
            self._conn.commit()
            return rows

    # Sessions -------------------------------------------------------------
    def create_session(self, title: str = "New chat") -> dict:
        sid, now = str(uuid.uuid4()), _now()
        self._execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (sid, title, now, now),
        )
        return self.get_session(sid)

    def get_session(self, session_id: str) -> dict | None:
        rows = self._execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(rows[0]) if rows else None

    def list_sessions(self) -> list[dict]:
        return [dict(r) for r in self._execute("SELECT * FROM sessions ORDER BY updated_at DESC")]

    def rename_session(self, session_id: str, title: str) -> None:
        self._execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), session_id),
        )

    def touch_session(self, session_id: str) -> None:
        self._execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))

    def delete_session(self, session_id: str) -> None:
        self._execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def update_summary(self, session_id: str, summary: str, summarized_count: int) -> None:
        self._execute(
            "UPDATE sessions SET summary = ?, summarized_count = ? WHERE id = ?",
            (summary, summarized_count, session_id),
        )

    # Messages -------------------------------------------------------------
    def add_message(self, session_id: str, role: str, content: str, meta: dict | None = None):
        mid = str(uuid.uuid4())
        self._execute(
            "INSERT INTO messages (id, session_id, role, content, meta, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mid, session_id, role, content, json.dumps(meta or {}), _now()),
        )
        self.touch_session(session_id)
        return mid

    def get_messages(self, session_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at, rowid",
            (session_id,),
        )
        out = []
        for r in rows:
            item = dict(r)
            item["meta"] = json.loads(item["meta"] or "{}")
            out.append(item)
        return out

    # Documents ------------------------------------------------------------
    def add_document(
        self, session_id: str, kind: str, source: str, title: str, chunks: int, chars: int
    ) -> dict:
        did = str(uuid.uuid4())
        self._execute(
            "INSERT INTO documents (id, session_id, kind, source, title, chunks, chars, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (did, session_id, kind, source, title, chunks, chars, _now()),
        )
        self.touch_session(session_id)
        return self.get_document(did)

    def get_document(self, document_id: str) -> dict | None:
        rows = self._execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        return dict(rows[0]) if rows else None

    def list_documents(self, session_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM documents WHERE session_id = ? ORDER BY created_at", (session_id,)
        )
        return [dict(r) for r in rows]

    def find_document(self, session_id: str, source: str) -> dict | None:
        rows = self._execute(
            "SELECT * FROM documents WHERE session_id = ? AND source = ?", (session_id, source)
        )
        return dict(rows[0]) if rows else None

    def delete_document(self, document_id: str) -> None:
        self._execute("DELETE FROM documents WHERE id = ?", (document_id,))
