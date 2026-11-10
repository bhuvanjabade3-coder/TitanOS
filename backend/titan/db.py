"""SQLite persistence with ordered, idempotent migrations."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# Append only. Never edit a migration that has shipped.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            outcome TEXT NOT NULL
        );
        CREATE INDEX idx_audit_ts ON audit_log(ts);
        """,
    ),
    (
        2,
        """
        CREATE TABLE approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            params TEXT NOT NULL,
            summary TEXT NOT NULL,
            risk TEXT NOT NULL,
            reasons TEXT NOT NULL,
            status TEXT NOT NULL,
            decided_at TEXT,
            result TEXT
        );
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            result TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            level TEXT NOT NULL,
            read INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            due_at TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE app_usage (
            app_id TEXT PRIMARY KEY,
            last_used TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE plugins (
            id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );
        """,
    ),
]


def now() -> str:
    return _now()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> int:
        """Apply pending migrations; returns the resulting schema version."""
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            current = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
        for version, sql in MIGRATIONS:
            if version <= current:
                continue
            conn = sqlite3.connect(self.path, timeout=10)
            try:
                # executescript wraps nothing itself; make each migration atomic.
                conn.executescript(
                    f"BEGIN;\n{sql}\n"
                    f"INSERT INTO schema_migrations VALUES ({version}, '{_now()}');\nCOMMIT;"
                )
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            current = version
        return current

    # --- generic helpers -------------------------------------------------
    def q(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def x(self, sql: str, params: tuple = ()) -> int:
        """Execute a write; returns lastrowid for INSERT, else rowcount."""
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            return int(cur.lastrowid) if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    def pref(self, key: str, default: Any = None) -> Any:
        try:
            return self.get_preference(key)
        except KeyError:
            return default

    # --- preferences -------------------------------------------------------
    def get_preferences(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM preferences ORDER BY key").fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def get_preference(self, key: str) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row["value"])

    def set_preference(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO preferences(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), _now()),
            )

    def delete_preference(self, key: str) -> bool:
        with self.connect() as conn:
            return conn.execute("DELETE FROM preferences WHERE key=?", (key,)).rowcount > 0

    # --- audit log ---------------------------------------------------------
    def audit(self, actor: str, action: str, detail: dict[str, Any], outcome: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO audit_log(ts, actor, action, detail, outcome) VALUES(?,?,?,?,?)",
                (_now(), actor, action, json.dumps(detail), outcome),
            )
            return int(cur.lastrowid)

    def audit_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]
