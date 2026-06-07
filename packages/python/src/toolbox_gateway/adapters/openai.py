"""OpenAI function calling adapter for Toolbox.

Converts the toolbox into a single OpenAI function definition and
provides a handler for tool call responses.
"""

from __future__ import annotations

import json
from typing import Any

from ..core import Toolbox, ToolboxCommand


class OpenAIAdapter:
    """Adapt Toolbox for OpenAI's function calling API.

    Usage::

        adapter = OpenAIAdapter(toolbox)

        # Get the function definition for your API call
        functions = [adapter.get_function_schema()]

        # When OpenAI returns a tool call, handle it:
        result = adapter.handle_tool_call(tool_call)
    """

    def __init__(self, toolbox: Toolbox) -> None:
        self.toolbox = toolbox

    def get_function_schema(self) -> dict[str, Any]:
        """Return the OpenAI function calling schema for toolbox."""
        defn = self.toolbox.get_tool_definition()
        return {
            "type": "function",
            "function": {
                "name": defn["name"],
                "description": defn["description"],
                "parameters": defn["parameters"],
            },
        }

    def handle_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Handle an OpenAI tool call response.

        Args:
            tool_call: The tool call object from OpenAI's response,
                       with 'function' containing 'arguments' as a JSON string.

        Returns:
            A dict suitable for sending back as a tool message.
        """
        arguments = json.loads(tool_call["function"]["arguments"])
        command = arguments.get("command", "")
        result = self.toolbox.handle(command=command, **arguments)

        return {
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "name": "toolbox",
            "content": json.dumps(result.to_dict()),
        }