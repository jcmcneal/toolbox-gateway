"""Toolbox — a single-tool gateway pattern for LLM agents."""

__version__ = "0.1.0"

from .core import Toolbox, Tool, is_available, is_gateway_call, unwrap_gateway_call, GATEWAY_TOOL_NAME
from .hints import HintStore, Hint, MemoryHintStore
from .backends.sqlite_store import SQLiteHintStore

__all__ = [
    "Toolbox",
    "Tool",
    "GATEWAY_TOOL_NAME",
    "is_available",
    "is_gateway_call",
    "unwrap_gateway_call",
    "HintStore",
    "Hint",
    "MemoryHintStore",
    "SQLiteHintStore",
]

# Opt-in: schema formatting utilities
# Usage: from toolbox_gateway.schema import schema_to_csv, schema_to_markdown, data_to_csv
# Requires: pip install toolbox-gateway[schema] (future: may add dependencies)