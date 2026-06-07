"""SQLite hint store — lightweight persistent hints with no external deps."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..hints import Hint, HintStore


DEFAULT_DB_PATH = ".toolbox/hints.db"


class SQLiteHintStore:
    """SQLite-backed hint store for production use.

    Zero external dependencies — uses Python's built-in sqlite3 module.
    Persists hints across restarts with no infrastructure requirements.

    Usage::

        store = SQLiteHintStore()                          # .toolbox/hints.db
        store = SQLiteHintStore(path="data/my_hints.db")   # custom path
    """

    def __init__(self, path: str = DEFAULT_DB_PATH) -> None:
        self._path = path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create the database and table if they don't exist."""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hints (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    hint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_hints_category_key
                ON hints (category, key)
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_hint(row: sqlite3.Row) -> Hint:
        return Hint(
            id=row["id"],
            category=row["category"],
            key=row["key"],
            hint=row["hint"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Interface ──────────────────────────────────────────────────

    def read(self, *, category: str | None = None, key: str | None = None) -> list[Hint]:
        with self._connect() as conn:
            query = "SELECT * FROM hints"
            conditions: list[str] = []
            params: list[str] = []

            if category:
                conditions.append("category = ?")
                params.append(category)
            if key:
                conditions.append("key = ?")
                params.append(key)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_hint(row) for row in rows]

    def get_by_id(self, hint_id: str) -> Optional[Hint]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM hints WHERE id = ?", (hint_id,)).fetchone()
            return self._row_to_hint(row) if row else None

    def create(self, *, category: str, key: str, hint: str) -> Hint:
        from uuid import uuid4

        with self._connect() as conn:
            # Check for existing (idempotent)
            existing = conn.execute(
                "SELECT * FROM hints WHERE category = ? AND key = ?",
                (category, key),
            ).fetchone()

            if existing:
                return self._row_to_hint(existing)

            now = datetime.now(timezone.utc).isoformat()
            hint_obj = Hint(id=str(uuid4()), category=category, key=key, hint=hint, created_at=now, updated_at=now)

            conn.execute(
                "INSERT INTO hints (id, category, key, hint, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (hint_obj.id, hint_obj.category, hint_obj.key, hint_obj.hint, hint_obj.created_at, hint_obj.updated_at),
            )

            return hint_obj

    def update(self, *, hint_id: str, hint: str) -> Optional[Hint]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE hints SET hint = ?, updated_at = ? WHERE id = ?",
                (hint, now, hint_id),
            )
            if cursor.rowcount == 0:
                return None

            row = conn.execute("SELECT * FROM hints WHERE id = ?", (hint_id,)).fetchone()
            return self._row_to_hint(row) if row else None

    def delete(self, *, hint_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM hints WHERE id = ?", (hint_id,))
            return cursor.rowcount > 0