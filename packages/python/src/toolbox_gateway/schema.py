"""Schema formatting — convert JSON Schemas to compact LLM-friendly formats.

Opt-in: ``pip install toolbox-gateway[schema]``

This module provides two key utilities:

1. ``schema_to_csv`` — Convert a JSON Schema to a compact CSV header with type hints
2. ``schema_to_markdown`` — Convert a JSON Schema to markdown field documentation

Both are designed for the ``toolbox explain`` command to return compact,
LLM-friendly tool documentation instead of raw JSON Schema blobs.
"""

from __future__ import annotations

from typing import Any, Optional


# ── Type hint extraction ─────────────────────────────────────────────

def _format_range_hint(
    min_val: int | float | None,
    max_val: int | float | None,
    prefix: str,
) -> str:
    if min_val is not None and max_val is not None:
        return f"{{{prefix}:{min_val}}}" if min_val == max_val else f"{{{prefix}:{min_val}-{max_val}}}"
    if min_val is not None:
        return f"{{{prefix}:{min_val}+}}"
    if max_val is not None:
        return f"{{{prefix}:≤{max_val}}}"
    return ""


def _get_length_hint(field_schema: dict[str, Any]) -> str:
    ftype = field_schema.get("type", "string")
    if ftype == "string":
        return _format_range_hint(field_schema.get("minLength"), field_schema.get("maxLength"), "len")
    if ftype in ("integer", "number"):
        return _format_range_hint(field_schema.get("minimum"), field_schema.get("maximum"), "range")
    if ftype == "array":
        return _format_range_hint(field_schema.get("minItems"), field_schema.get("maxItems"), "len")
    return ""


def _parse_metadata_hints(description: str | None) -> str:
    """Extract metadata hints from description like 'format:OCC|pattern:^[A-Z]+$'."""
    if not description:
        return ""
    import re
    match = re.search(r"\(([^)]+)\)", description)
    if not match:
        return ""
    metadata_str = match.group(1)
    hints: list[str] = []
    for part in metadata_str.split("|"):
        pieces = part.split(":", 1)
        if len(pieces) == 2:
            hints.append(f"{{{pieces[0]}:{pieces[1]}}}")
    return "".join(hints)


def _get_type_hint(field_schema: dict[str, Any], include_format: bool = True) -> str:
    """Extract a compact type hint string from a JSON Schema field definition."""
    length_hint = _get_length_hint(field_schema)
    metadata_hints = _parse_metadata_hints(field_schema.get("description"))

    def append_hints(base: str) -> str:
        return base + length_hint + metadata_hints

    # Enum
    if "enum" in field_schema:
        return append_hints("|".join(str(v) for v in field_schema["enum"]))

    # Array
    if field_schema.get("type") == "array":
        items = field_schema.get("items", {})
        if items:
            elem_type = _get_type_hint(items, include_format=False)
            return append_hints(f"array({elem_type})")
        return append_hints("array")

    # Object with properties
    if field_schema.get("type") == "object" and "properties" in field_schema:
        required = set(field_schema.get("required", []))
        fields = []
        for key, prop in field_schema["properties"].items():
            prop_type = _get_type_hint(prop, include_format=False)
            suffix = "" if key in required else "?"
            fields.append(f"{key}{suffix}:{prop_type}")
        return append_hints(f"object({', '.join(fields)})")

    # Object without properties (dict/record)
    if field_schema.get("type") == "object":
        return append_hints("json")

    # Primitives
    type_map = {"string": "string", "number": "number", "integer": "integer", "boolean": "boolean"}
    return append_hints(type_map.get(field_schema.get("type", "string"), "string"))


# ── CSV Schema ────────────────────────────────────────────────────────

def schema_to_csv(
    schema: dict[str, Any],
    *,
    comment: str | None = None,
) -> str:
    """Convert a JSON Schema to a compact CSV header line with type hints.

    Produces output like::

        # Schema: name (string), age (integer)?, role (enum:admin|user)
        name,age,role

    Args:
        schema: A JSON Schema dict (type: object with properties, or type: array with items).
        comment: Optional label for the schema comment line.

    Returns:
        CSV schema string suitable for LLM consumption.
    """
    resolved = _resolve_ref(schema)

    properties: dict[str, Any] = {}
    required: list[str] = []

    if resolved.get("type") == "array" and "items" in resolved:
        properties = resolved["items"].get("properties", {})
        required = resolved["items"].get("required", [])
    elif resolved.get("type") == "object":
        properties = resolved.get("properties", {})
        required = resolved.get("required", [])
    elif "properties" in resolved:
        properties = resolved["properties"]
        required = resolved.get("required", [])

    if not properties:
        raise ValueError(f"Schema must have properties (object or array with items). Got: {list(resolved.keys())}")

    fields: list[str] = []
    type_hints: list[str] = []
    optionals: list[bool] = []

    for field_name, field_schema in properties.items():
        fields.append(field_name)
        is_optional = field_name not in required
        optionals.append(is_optional)
        type_hints.append(_get_type_hint(field_schema))

    # Build schema comment
    schema_parts = [
        f"{fields[i]} ({type_hints[i]}){'?' if optionals[i] else ''}"
        for i in range(len(fields))
    ]
    comment_line = f"# {comment}: " if comment else "# Schema: "
    header_line = ",".join(fields)

    return f"{comment_line}{', '.join(schema_parts)}\n{header_line}"


# ── Markdown Schema ───────────────────────────────────────────────────

def schema_to_markdown(
    schema: dict[str, Any],
    *,
    title: str | None = None,
    description: str | None = None,
) -> str:
    """Convert a JSON Schema to markdown field documentation.

    Produces output like::

        ### MyTool Schema (my_tool)[Get data from the API]

        (This tool uses a method-based API. Specify the 'method' parameter to choose the operation)
        **Fields:**
        - `name` (string): The name of the thing
        - `limit` (integer){range:1-100}?: Max items to return
        - `method` (enum:read|write): Operation to perform

    Args:
        schema: A JSON Schema dict (type: object with properties).
        title: Optional tool name.
        description: Optional tool description.

    Returns:
        Markdown documentation string.
    """
    resolved = _resolve_ref(schema)

    properties = resolved.get("properties", {})
    required = set(resolved.get("required", []))

    lines: list[str] = []

    # Header
    header = "### Tool Schema"
    if title:
        header = f"### {title}"
    if description:
        header += f"[{description}]"
    lines.append(header)

    # Check for method-based API
    method_field = properties.get("method", {})
    if "enum" in method_field:
        lines.append("(This tool uses a method-based API. Specify the 'method' parameter to choose the operation)")

    # Fields
    if properties:
        lines.append("**Fields:**")
        for field_name, field_schema in properties.items():
            type_hint = _get_type_hint(field_schema)
            is_required = field_name in required
            desc = field_schema.get("description", "").strip()

            # Clean up description — strip metadata hints already captured in type
            clean_desc = _parse_metadata_hints(field_schema.get("description"))
            if clean_desc:
                # Remove the (format:...|pattern:...) part from description
                import re
                desc = re.sub(r"\([^)]*(?:format|pattern)[^)]*\)", "", desc).strip()

            suffix = "" if is_required else "?"
            line = f"- `{field_name}` ({type_hint}){suffix}"
            if desc:
                line += f": {desc}"
            lines.append(line)

    return "\n".join(lines)


# ── JSON to CSV data format ──────────────────────────────────────────

def data_to_csv(
    data: list[dict[str, Any]],
    *,
    columns: list[str] | None = None,
    include_header: bool = True,
    fence_block: str | None = None,
) -> str:
    """Convert a list of dicts to CSV format for LLM consumption.

    Args:
        data: List of row dicts.
        columns: Optional column order. Auto-detected from data if omitted.
        include_header: Whether to include a header row.
        fence_block: Optional label to wrap in a ```csv comment block.

    Returns:
        CSV string.
    """
    if not data:
        return ""

    # Determine columns
    if not columns:
        seen: list[str] = []
        for row in data:
            for key in row:
                if key not in seen:
                    seen.append(key)
        columns = seen

    lines: list[str] = []

    if include_header:
        lines.append(",".join(columns))

    for row in data:
        values = [_escape_csv_field(row.get(col, "")) for col in columns]
        lines.append(",".join(values))

    csv_text = "\n".join(lines)

    if fence_block:
        return f"```csv\n# {fence_block}\n{csv_text}\n```"

    return csv_text


# ── Internal helpers ──────────────────────────────────────────────────

def _resolve_ref(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref references in a JSON Schema."""
    if "$ref" in schema and "definitions" in schema:
        ref_path = schema["$ref"].replace("#/definitions/", "")
        return schema.get("definitions", {}).get(ref_path, schema)
    return schema


def _escape_csv_field(value: Any) -> str:
    """Escape a single value for CSV output."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        import json
        s = json.dumps(value, separators=(",", ":"))
        if "," in s or '"' in s or "\n" in s:
            return f'"{s.replace(chr(34), chr(34) + chr(34))}"'
        return s
    s = str(value)
    if "," in s or '"' in s or "\n" in s:
        return f'"{s.replace(chr(34), chr(34) + chr(34))}"'
    return s