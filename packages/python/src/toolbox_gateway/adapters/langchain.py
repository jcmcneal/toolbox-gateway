"""LangChain adapter for Toolbox.

Converts the toolbox into a single LangChain BaseTool instance.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..core import Toolbox


class LangChainAdapter:
    """Adapt Toolbox as a single LangChain tool.

    Requires langchain-core to be installed.

    Usage::

        adapter = LangChainAdapter(toolbox)
        tool = adapter.as_tool()

        # Use in a LangChain agent
        agent = create_react_agent(llm, [tool], prompt)
    """

    def __init__(self, toolbox: Toolbox) -> None:
        self.toolbox = toolbox

    def as_tool(self) -> Any:
        """Return a LangChain BaseTool wrapping the toolbox.

        Raises ImportError if langchain-core is not installed.
        """
        try:
            from langchain_core.tools import StructuredTool
        except ImportError as e:
            raise ImportError(
                "langchain-core is required for the LangChain adapter. "
                "Install it with: pip install langchain-core"
            ) from e

        def _run(command: str, **kwargs: Any) -> str:
            result = self.toolbox.handle(command=command, **kwargs)
            return json.dumps(result.to_dict(), default=str)

        async def _arun(command: str, **kwargs: Any) -> str:
            # Synchronous fallback — async execute is not yet supported
            return _run(command, **kwargs)

        defn = self.toolbox.get_tool_definition()
        params = defn["parameters"]

        return StructuredTool.from_function(
            func=_run,
            coroutine=_arun,
            name=defn["name"],
            description=defn["description"],
            args_schema=_build_pydantic_schema(params),
        )


def _build_pydantic_schema(json_schema: dict[str, Any]) -> Any:
    """Convert a JSON Schema to a Pydantic model for LangChain."""
    try:
        from pydantic import BaseModel, Field, create_model
    except ImportError:
        raise ImportError("pydantic is required for the LangChain adapter")

    properties = json_schema.get("properties", {})
    required = set(json_schema.get("required", []))

    fields: dict[str, Any] = {}
    for name, prop in properties.items():
        field_type = _json_type_to_python(prop)
        is_required = name in required

        if is_required:
            fields[name] = (field_type, Field(description=prop.get("description", "")))
        else:
            fields[name] = (Optional[field_type], Field(default=None, description=prop.get("description", "")))

    return create_model("ToolboxInput", **fields)


def _json_type_to_python(prop: dict[str, Any]) -> type:
    """Map JSON Schema types to Python types."""
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    json_type = prop.get("type", "string")
    return type_map.get(json_type, str)