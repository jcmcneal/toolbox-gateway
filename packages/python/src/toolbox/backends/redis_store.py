"""Redis hint store — production-grade persistent hints with TTL."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from ..hints import Hint, HintStore


class RedisHintStore:
    """Redis-backed hint store for production use.

    Hints are stored with a configurable TTL (default 30 days).
    Uses SCAN for key discovery to avoid blocking Redis.

    Requires the ``redis`` package: pip install redis

    Usage::

        import redis
        client = redis.Redis(host="localhost", port=6379, db=0)
        store = RedisHintStore(client)
    """

    KEY_PREFIX = "tool-hints"
    DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

    def __init__(self, client: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._redis = client
        self._ttl = ttl_seconds

    # ── Key helpers ────────────────────────────────────────────────

    def _id_key(self, hint_id: str) -> str:
        return f"{self.KEY_PREFIX}:id:{hint_id}"

    def _index_key(self, category: str, key: str) -> str:
        return f"{self.KEY_PREFIX}:index:{category}:{key}"

    # ── Interface ──────────────────────────────────────────────────

    def read(self, *, category: str | None = None, key: str | None = None) -> list[Hint]:
        all_hints = self._get_all_hints()
        if category:
            all_hints = [h for h in all_hints if h.category == category]
        if key:
            all_hints = [h for h in all_hints if h.key == key]
        return all_hints

    def get_by_id(self, hint_id: str) -> Optional[Hint]:
        data = self._redis.get(self._id_key(hint_id))
        if data:
            return Hint(**json.loads(data))
        return None

    def create(self, *, category: str, key: str, hint: str) -> Hint:
        # Idempotent: check for existing hint with same category+key
        existing_id = self._redis.get(self._index_key(category, key))
        if existing_id:
            existing_data = self._redis.get(self._id_key(existing_id.decode() if isinstance(existing_id, bytes) else existing_id))
            if existing_data:
                return Hint(**json.loads(existing_data))

        from uuid import uuid4
        now = datetime.now(timezone.utc).isoformat()
        hint_obj = Hint(id=str(uuid4()), category=category, key=key, hint=hint, created_at=now, updated_at=now)

        id_key = self._id_key(hint_obj.id)
        idx_key = self._index_key(category, key)

        self._redis.setex(id_key, self._ttl, json.dumps({
            "id": hint_obj.id, "category": hint_obj.category,
            "key": hint_obj.key, "hint": hint_obj.hint,
            "created_at": hint_obj.created_at, "updated_at": hint_obj.updated_at,
        }))
        self._redis.setex(idx_key, self._ttl, hint_obj.id)

        return hint_obj

    def update(self, *, hint_id: str, hint: str) -> Optional[Hint]:
        data = self._redis.get(self._id_key(hint_id))
        if not data:
            return None

        existing = Hint(**json.loads(data))
        updated = Hint(
            id=existing.id, category=existing.category, key=existing.key,
            hint=hint, created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        id_key = self._id_key(updated.id)
        self._redis.setex(id_key, self._ttl, json.dumps({
            "id": updated.id, "category": updated.category,
            "key": updated.key, "hint": updated.hint,
            "created_at": updated.created_at, "updated_at": updated.updated_at,
        }))

        return updated

    def delete(self, *, hint_id: str) -> bool:
        data = self._redis.get(self._id_key(hint_id))
        if not data:
            return False

        existing = Hint(**json.loads(data))
        self._redis.delete(self._id_key(hint_id))
        self._redis.delete(self._index_key(existing.category, existing.key))
        return True

    # ── Internals ──────────────────────────────────────────────────

    def _get_all_hints(self) -> list[Hint]:
        """Use SCAN to discover all hint keys without blocking."""
        hints: list[Hint] = []
        pattern = f"{self.KEY_PREFIX}:id:*"
        cursor = 0

        while True:
            cursor, keys = self._redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                data = self._redis.get(key_str)
                if data:
                    hints.append(Hint(**json.loads(data)))
            if cursor == 0:
                break

        return hints