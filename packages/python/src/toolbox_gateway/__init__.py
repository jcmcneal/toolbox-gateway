"""Toolbox — a single-tool gateway pattern for LLM agents."""

__version__ = "0.3.0"

from .core import (
    Toolbox,
    Tool,
    GATEWAY_TOOL_NAME,
    RESERVED_COMMAND_NAMES,
    TOOLSET_DEFINITION,
    detail_for_command,
    filter_to_gateway_only,
    is_available,
    is_gateway_call,
    label_for_command,
    preview_for_command,
    should_collapse_to_gateway,
    spinner_label,
    unwrap_gateway_call,
    unwrap_with_subject,
)
from .hints import HintStore, Hint, MemoryHintStore
from .backends.sqlite_store import SQLiteHintStore

__all__ = [
    "Toolbox",
    "Tool",
    "GATEWAY_TOOL_NAME",
    "RESERVED_COMMAND_NAMES",
    "TOOLSET_DEFINITION",
    "detail_for_command",
    "filter_to_gateway_only",
    "is_available",
    "is_gateway_call",
    "label_for_command",
    "preview_for_command",
    "should_collapse_to_gateway",
    "spinner_label",
    "unwrap_gateway_call",
    "unwrap_with_subject",
    "HintStore",
    "Hint",
    "MemoryHintStore",
    "SQLiteHintStore",
]

# Opt-in: schema formatting utilities
# Usage: from toolbox_gateway.schema import schema_to_csv, schema_to_markdown, data_to_csv
# Requires: pip install toolbox-gateway[schema] (future: may add dependencies)