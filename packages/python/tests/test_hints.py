"""Tests for the hint store backends."""

import pytest

from toolbox.hints import Hint, MemoryHintStore


class TestMemoryHintStore:
    def test_create_and_read(self):
        store = MemoryHintStore()
        hint = store.create(category="tool", key="get_quote", hint="Requires uppercase tickers")

        assert hint.id
        assert hint.category == "tool"
        assert hint.key == "get_quote"
        assert hint.hint == "Requires uppercase tickers"

    def test_read_all(self):
        store = MemoryHintStore()
        store.create(category="tool", key="a", hint="Hint A")
        store.create(category="general", key="b", hint="Hint B")

        all_hints = store.read()
        assert len(all_hints) == 2

    def test_read_by_category(self):
        store = MemoryHintStore()
        store.create(category="tool", key="a", hint="Hint A")
        store.create(category="general", key="b", hint="Hint B")

        tool_hints = store.read(category="tool")
        assert len(tool_hints) == 1
        assert tool_hints[0].category == "tool"

    def test_read_by_category_and_key(self):
        store = MemoryHintStore()
        store.create(category="tool", key="a", hint="Hint A")
        store.create(category="tool", key="b", hint="Hint B")

        specific = store.read(category="tool", key="b")
        assert len(specific) == 1
        assert specific[0].key == "b"

    def test_get_by_id(self):
        store = MemoryHintStore()
        created = store.create(category="tool", key="x", hint="Found me")

        found = store.get_by_id(created.id)
        assert found is not None
        assert found.hint == "Found me"

    def test_get_by_id_not_found(self):
        store = MemoryHintStore()
        assert store.get_by_id("nonexistent") is None

    def test_update(self):
        store = MemoryHintStore()
        created = store.create(category="tool", key="a", hint="Old")

        updated = store.update(hint_id=created.id, hint="New")
        assert updated is not None
        assert updated.hint == "New"
        assert updated.id == created.id

    def test_update_nonexistent(self):
        store = MemoryHintStore()
        result = store.update(hint_id="ghost", hint="Nope")
        assert result is None

    def test_delete(self):
        store = MemoryHintStore()
        created = store.create(category="tool", key="a", hint="Bye")

        assert store.delete(hint_id=created.id) is True
        assert store.get_by_id(created.id) is None

    def test_delete_nonexistent(self):
        store = MemoryHintStore()
        assert store.delete(hint_id="ghost") is False

    def test_idempotent_create(self):
        """Same category+key returns existing hint, doesn't duplicate."""
        store = MemoryHintStore()
        first = store.create(category="tool", key="dedup", hint="First")
        second = store.create(category="tool", key="dedup", hint="Second")

        assert first.id == second.id
        assert second.hint == "First"  # Not overwritten