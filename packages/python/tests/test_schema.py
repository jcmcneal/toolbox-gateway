"""Tests for the schema formatting module."""

import pytest

from toolbox_gateway.schema import schema_to_csv, schema_to_markdown, data_to_csv


# ── Fixtures ──────────────────────────────────────────────────────────

SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "The name"},
        "age": {"type": "integer", "description": "Age in years"},
        "role": {"type": "string", "enum": ["admin", "user"], "description": "User role"},
    },
    "required": ["name", "role"],
}

NESTED_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "Ticker symbol"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max results"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Filter tags",
        },
        "metadata": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "version": {"type": "integer"},
            },
            "description": "Extra metadata",
        },
    },
    "required": ["symbol"],
}

ARRAY_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["BUY", "SELL"]},
            "ticker": {"type": "string"},
        },
        "required": ["action", "ticker"],
    },
}


# ── schema_to_csv ─────────────────────────────────────────────────────

class TestSchemaToCsv:
    def test_simple_schema(self):
        result = schema_to_csv(SIMPLE_SCHEMA)
        assert "# Schema:" in result
        assert "name" in result
        assert "age" in result
        assert "role" in result
        assert "admin|user" in result  # enum hint

    def test_required_vs_optional(self):
        result = schema_to_csv(SIMPLE_SCHEMA)
        # name is required (no ?), age is optional (?)
        lines = result.split("\n")
        comment = lines[0]
        assert "(string)" in comment  # name type, no ?
        assert "(integer)?" in comment  # age is optional

    def test_custom_comment(self):
        result = schema_to_csv(SIMPLE_SCHEMA, comment="My Tool")
        assert "# My Tool:" in result

    def test_nested_object(self):
        result = schema_to_csv(NESTED_SCHEMA)
        # Nested object fields show type structure; optional fields get ? since
        # the NESTED_SCHEMA doesn't list source/version as required
        assert "object(" in result
        assert "source" in result
        assert "version" in result

    def test_nested_array(self):
        result = schema_to_csv(NESTED_SCHEMA)
        assert "array(string)" in result

    def test_range_hints(self):
        result = schema_to_csv(NESTED_SCHEMA)
        assert "{range:1-100}" in result

    def test_array_schema(self):
        result = schema_to_csv(ARRAY_SCHEMA)
        assert "# Schema:" in result
        assert "action" in result
        assert "BUY|SELL" in result

    def test_header_line_present(self):
        result = schema_to_csv(SIMPLE_SCHEMA)
        lines = result.strip().split("\n")
        header = lines[-1]
        fields = header.split(",")
        assert "name" in fields
        assert "age" in fields
        assert "role" in fields


# ── schema_to_markdown ───────────────────────────────────────────────

class TestSchemaToMarkdown:
    def test_simple_schema(self):
        result = schema_to_markdown(SIMPLE_SCHEMA, title="MyTool", description="A test tool")
        assert "### MyTool" in result
        assert "A test tool" in result
        assert "**Fields:**" in result
        assert "`name`" in result
        assert "`age`" in result

    def test_required_optional_marking(self):
        result = schema_to_markdown(SIMPLE_SCHEMA)
        # name is required, age is optional
        assert "- `name` (string):" in result
        assert "- `age` (integer)?:" in result

    def test_enum_shown(self):
        result = schema_to_markdown(SIMPLE_SCHEMA)
        assert "admin|user" in result

    def test_method_based_api_detection(self):
        schema_with_method = {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["READ", "CREATE"]},
                "data": {"type": "string"},
            },
            "required": ["method"],
        }
        result = schema_to_markdown(schema_with_method)
        assert "method-based API" in result

    def test_range_constraint(self):
        result = schema_to_markdown(NESTED_SCHEMA, title="Nested")
        assert "{range:1-100}" in result

    def test_nested_types_displayed(self):
        result = schema_to_markdown(NESTED_SCHEMA)
        assert "array(string)" in result
        assert "object(" in result


# ── data_to_csv ──────────────────────────────────────────────────────

class TestDataToCsv:
    def test_simple_data(self):
        data = [
            {"name": "AAPL", "price": 175.50},
            {"name": "GOOG", "price": 140.20},
        ]
        result = data_to_csv(data)
        assert "name,price" in result
        assert "AAPL" in result
        assert "GOOG" in result

    def test_with_fence_block(self):
        data = [{"name": "test"}]
        result = data_to_csv(data, fence_block="Available Tools")
        assert "```csv" in result
        assert "# Available Tools" in result
        assert "```" in result

    def test_empty_data(self):
        result = data_to_csv([])
        assert result == ""

    def test_none_values(self):
        data = [{"name": "test", "price": None}]
        result = data_to_csv(data)
        assert "test" in result

    def test_nested_objects_json_serialized(self):
        data = [{"name": "test", "meta": {"key": "val"}}]
        result = data_to_csv(data)
        # JSON objects are CSV-escaped (quotes doubled inside quoted fields)
        assert "key" in result
        assert "val" in result

    def test_custom_columns(self):
        data = [{"a": 1, "b": 2, "c": 3}]
        result = data_to_csv(data, columns=["c", "a"])
        lines = result.strip().split("\n")
        assert lines[0] == "c,a"

    def test_boolean_values(self):
        data = [{"name": "test", "active": True}]
        result = data_to_csv(data)
        assert "true" in result