"""Hint store — learned usage patterns, gotchas, and shortcuts for tools."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol


@dataclass
class Hint:
    """A single hint about tool usage."""

    id: str
    category: str  # "tool", "mcp-server", "mcp-tool", "general"
    key: str  # tool name, server ID, or topic
    hint: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HintStore(Protocol):
    """Protocol for hint storage backends.

    Implement this to plug in Redis, SQLite, or any other backend.
    """

    def read(self, *, category: str | None = None, key: str | None = None) -> list[Hint]: ...
    def get_by_id(self, hint_id: str) -> Optional[Hint]: ...
    def create(self, *, category: str, key: str, hint: str) -> Hint: ...
    def update(self, *, hint_id: str, hint: str) -> Optional[Hint]: ...
    def delete(self, *, hint_id: str) -> bool: ...


class MemoryHintStore:
    """In-memory hint store for development and testing."""

    def __init__(self) -> None:
        self._hints: dict[str, Hint] = {}

    def read(self, *, category: str | None = None, key: str | None = None) -> list[Hint]:
        hints = list(self._hints.values())
        if category:
            hints = [h for h in hints if h.category == category]
        if key:
            hints = [h for h in hints if h.key == key]
        return hints

    def get_by_id(self, hint_id: str) -> Optional[Hint]:
        return self._hints.get(hint_id)

    def create(self, *, category: str, key: str, hint: str) -> Hint:
        # Idempotent: if category+key already exists, return existing
        existing = self._find_by_category_key(category, key)
        if existing:
            return existing

        hint_obj = Hint(id=str(uuid.uuid4()), category=category, key=key, hint=hint)
        self._hints[hint_obj.id] = hint_obj
        return hint_obj

    def update(self, *, hint_id: str, hint: str) -> Optional[Hint]:
        existing = self._hints.get(hint_id)
        if not existing:
            return None

        updated = Hint(
            id=existing.id,
            category=existing.category,
            key=existing.key,
            hint=hint,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._hints[hint_id] = updated
        return updated

    def delete(self, *, hint_id: str) -> bool:
        if hint_id in self._hints:
            del self._hints[hint_id]
            return True
        return False

    def _find_by_category_key(self, category: str, key: str) -> Optional[Hint]:
        for hint in self._hints.values():
            if hint.category == category and hint.key == key:
                return hint
        return None