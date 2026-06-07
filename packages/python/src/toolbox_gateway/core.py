"""Core Toolbox — single-tool gateway for LLM agents."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Callable, Optional

from .hints import HintStore, Hint, MemoryHintStore
from .mcp import MCPRegistry, MCPServerInfo


def _serialize(obj: Any) -> Any:
    """Recursively serialize dataclasses, dicts, and lists to plain dicts."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


class ToolboxCommand(str, Enum):
    """Commands supported by the toolbox."""

    LIST = "list"
    EXPLAIN = "explain"
    RUN = "run"
    SERVERS = "servers"
    HINTS = "hints"


@dataclass
class Tool:
    """A tool that can be discovered and executed via toolbox."""

    name: str
    description: str
    schema: dict[str, Any] = field(default_factory=dict)
    execute: Callable[[dict[str, Any]], Any] = field(default=lambda _: {"error": "Not implemented"})
    is_hidden: bool = False  # Hidden tools won't appear in list, but can be run directly


@dataclass
class ToolResult:
    """Result from a toolbox command."""

    success: bool = True
    data: Any = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None

    def __post_init__(self):
        if self.data is not None:
            self.data = _serialize(self.data)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result


class Toolbox:
    """Single-tool gateway for LLM agents.

    Instead of exposing N tool schemas in the system prompt, expose 1 tool
    definition (toolbox) and let the agent discover, inspect, and execute
    tools on demand.

    Usage::

        toolbox = Toolbox(tools=[...], hint_store=MemoryHintStore())
        schema = toolbox.get_tool_definition()

        # When the LLM calls toolbox, route through handle():
        result = toolbox.handle(command="list")
    """

    def __init__(
        self,
        tools: list[Tool],
        hint_store: Optional[HintStore] = None,
        mcp_registry: Optional[MCPRegistry] = None,
        schema_format: str = "json",  # "json" (default) or "markdown" (opt-in, uses schema module)
    ):
        self._tools: dict[str, Tool] = {t.name: t for t in tools}
        self._hint_store = hint_store or MemoryHintStore()
        self._mcp_registry = mcp_registry
        self._schema_format = schema_format

    @classmethod
    def from_definitions(
        cls,
        definitions: list[dict],
        dispatcher: Callable[[str, dict], Any],
        hint_store: Optional[HintStore] = None,
        schema_format: str = "markdown",
    ) -> "Toolbox":
        """Build a Toolbox from external tool definitions.

        Each definition dict should have:
        - ``name``: tool name
        - ``description``: short description for the LLM
        - ``schema``: JSON Schema dict for the tool's parameters

        The *dispatcher* is called as ``dispatcher(name, args)`` to execute
        each tool. Use it to bridge to a host application's tool registry.

        Useful for host apps that already have a tool registry and don't
        want to translate entries into ``Tool`` objects manually.
        """
        tools = [
            Tool(
                name=d["name"],
                description=d.get("description", ""),
                schema=d.get("schema", {}),
                execute=lambda args, _name=d["name"], **kw: dispatcher(_name, args),
            )
            for d in definitions
        ]
        return cls(tools=tools, hint_store=hint_store, schema_format=schema_format)

    # ── Tool Definition ──────────────────────────────────────────────

    @classmethod
    def get_tool_definition(cls) -> dict[str, Any]:
        """Return the single tool schema to include in your LLM's tool list.

        This is the ONLY schema that goes in the system prompt. All other
        tools are discovered at runtime via the `list` and `explain` commands.
        """
        return {
            "name": "toolbox",
            "description": (
                "CLI-style gateway for all tools.\n\n"
                "Commands:\n"
                "- list: Show all available tools with descriptions "
                "(use --mcp=serverId for MCP tools)\n"
                "- explain: Get schema docs for one or more tools "
                "(provide toolNames, use --mcp=serverId for MCP tools)\n"
                "- run: Execute a tool (requires toolName and subject, "
                "use --mcp=serverId for MCP tools)\n"
                "- servers: List available MCP servers and their descriptions\n"
                "- hints: Manage universal hints for tool usage, gotchas, "
                "and MCP shortcuts (method: READ|CREATE|UPDATE|DELETE)\n\n"
                "Always provide a \"subject\" when using \"run\" to explain your intent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["list", "explain", "run", "servers", "hints"],
                        "description": "list | explain | run | servers | hints",
                    },
                    "toolNames": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tools to explain (for explain command, accepts multiple)",
                    },
                    "toolName": {
                        "type": "string",
                        "description": "Tool to run (for run command)",
                    },
                    "subject": {
                        "type": "string",
                        "minLength": 5,
                        "maxLength": 80,
                        "description": (
                            "One-liner description of what you are doing. No more than 10 words. "
                            "Do not reveal internal tool names or how it's handled internally."
                        ),
                    },
                    "args": {
                        "type": "object",
                        "description": "Tool arguments (for run command)",
                    },
                    "mcp": {
                        "type": "string",
                        "description": "MCP server ID to route command to (required for MCP tools)",
                    },
                },
                "required": ["command"],
            },
        }

    # ── Command Handlers ─────────────────────────────────────────────

    def handle(self, *, command: str, **kwargs: Any) -> ToolResult:
        """Route a toolbox command to the appropriate handler.

        This is the main entry point. Parse the LLM's tool call arguments
        and pass them here.
        """
        try:
            cmd = ToolboxCommand(command)
        except ValueError:
            return ToolResult(success=False, error=f"Unknown command: {command}")

        handlers = {
            ToolboxCommand.LIST: self._handle_list,
            ToolboxCommand.EXPLAIN: self._handle_explain,
            ToolboxCommand.RUN: self._handle_run,
            ToolboxCommand.SERVERS: self._handle_servers,
            ToolboxCommand.HINTS: self._handle_hints,
        }
        return handlers[cmd](**kwargs)

    # ── List ──────────────────────────────────────────────────────────

    def _handle_list(self, *, mcp: str | None = None, **_: Any) -> ToolResult:
        if mcp:
            return self._list_mcp_tools(mcp)

        tools = [
            {"name": name, "description": t.description}
            for name, t in self._tools.items()
            if not t.is_hidden
        ]

        result_data: dict[str, Any] = {"tools": tools, "count": len(tools)}

        if self._schema_format == "markdown":
            # Opt-in: compact CSV format for tool listing
            from .schema import data_to_csv
            csv = data_to_csv(tools, fence_block="Available Tools")
            result_data["markdown"] = csv

        return ToolResult(success=True, data=result_data)

    def _list_mcp_tools(self, server_id: str) -> ToolResult:
        if not self._mcp_registry:
            return ToolResult(success=False, error="No MCP registry configured")

        try:
            server = self._mcp_registry.get_server(server_id)
            if not server:
                return ToolResult(success=False, error=f"MCP server not found: {server_id}")

            tools = [
                {"name": t["name"], "description": t.get("description", "")}
                for t in server.list_tools()
            ]
            return ToolResult(success=True, data={"tools": tools, "count": len(tools), "mcp": server_id})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list MCP tools for {server_id}: {e}")

    # ── Explain ───────────────────────────────────────────────────────

    def _handle_explain(self, *, toolNames: list[str] | None = None, format: str | None = None, mcp: str | None = None, **_: Any) -> ToolResult:
        names = toolNames or []
        if not names:
            return ToolResult(success=False, error="explain requires at least one tool name in toolNames")

        if mcp:
            return self._explain_mcp_tools(names, mcp)

        # Per-call format override: 'json' forces raw schema regardless of default
        use_markdown = self._schema_format == "markdown" and format != "json"

        explanations = {}
        not_found = []

        for name in names:
            tool = self._tools.get(name)
            if tool:
                if use_markdown:
                    from .schema import schema_to_markdown

                    md = schema_to_markdown(
                        tool.schema,
                        title=name,
                        description=tool.description,
                    )
                    explanations[name] = {"markdown": md, "description": tool.description}
                else:
                    # Default: raw JSON schema
                    explanations[name] = {
                        "description": tool.description,
                        "schema": tool.schema,
                    }
            else:
                not_found.append(name)

        result_data: dict[str, Any] = {"explanations": explanations}
        if not_found:
            result_data["not_found"] = not_found

        if not explanations:
            return ToolResult(success=False, error=f"Tools not found: {', '.join(not_found)}")

        return ToolResult(success=True, data=result_data)

    def _explain_mcp_tools(self, names: list[str], server_id: str) -> ToolResult:
        if not self._mcp_registry:
            return ToolResult(success=False, error="No MCP registry configured")

        try:
            server = self._mcp_registry.get_server(server_id)
            if not server:
                return ToolResult(success=False, error=f"MCP server not found: {server_id}")

            return ToolResult(success=True, data=server.explain_tools(names))
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to explain MCP tools for {server_id}: {e}")

    # ── Run ───────────────────────────────────────────────────────────

    def _handle_run(
        self,
        *,
        toolName: str | None = None,
        subject: str | None = None,
        args: dict[str, Any] | None = None,
        mcp: str | None = None,
        **_: Any,
    ) -> ToolResult:
        if not toolName:
            return ToolResult(success=False, error="run requires toolName")
        if not subject:
            return ToolResult(success=False, error="run requires subject — explain what you are doing")

        start = time.monotonic()

        if mcp:
            result = self._run_mcp_tool(toolName, args or {}, mcp)
        else:
            result = self._run_native_tool(toolName, args or {})

        duration_ms = int((time.monotonic() - start) * 1000)
        result.duration_ms = duration_ms
        return result

    def _run_native_tool(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Native tool not found: {tool_name}")

        try:
            output = tool.execute(args)
            return ToolResult(success=True, data={"result": output, "tool_name": tool_name, "source": "native"})
        except Exception as e:
            return ToolResult(success=False, error=f"Tool execution failed: {e}", data={"tool_name": tool_name})

    def _run_mcp_tool(self, tool_name: str, args: dict[str, Any], server_id: str) -> ToolResult:
        if not self._mcp_registry:
            return ToolResult(success=False, error="No MCP registry configured")

        try:
            server = self._mcp_registry.get_server(server_id)
            if not server:
                return ToolResult(success=False, error=f"MCP server not found: {server_id}")

            output = server.execute_tool(tool_name, args)
            return ToolResult(success=True, data={"result": output, "tool_name": tool_name, "source": "mcp"})
        except Exception as e:
            return ToolResult(success=False, error=f"MCP tool execution failed: {e}", data={"tool_name": tool_name})

    # ── Servers ───────────────────────────────────────────────────────

    def _handle_servers(self, **_: Any) -> ToolResult:
        if not self._mcp_registry:
            return ToolResult(success=False, error="No MCP registry configured")

        servers = self._mcp_registry.list_servers()
        return ToolResult(success=True, data={"servers": servers, "count": len(servers)})

    # ── Hints ─────────────────────────────────────────────────────────

    def _handle_hints(self, *, args: dict[str, Any] | None = None, **_: Any) -> ToolResult:
        args = args or {}
        method = args.get("method")

        if not method:
            # Return the schema so the agent knows how to use hints
            return ToolResult(
                success=True,
                data={
                    "description": "Manage universal hints for tool usage, gotchas, and MCP shortcuts.",
                    "schema": {
                        "method": {
                            "type": "enum",
                            "values": ["READ", "CREATE", "UPDATE", "DELETE"],
                            "required": True,
                            "description": "Operation to perform",
                        },
                        "category": {
                            "type": "enum",
                            "values": ["tool", "mcp-server", "mcp-tool", "general"],
                            "required": "for CREATE, optional filter for READ",
                            "description": "Hint category",
                        },
                        "key": {
                            "type": "string",
                            "required": "for CREATE, optional filter for READ",
                            "description": "Tool name, server ID, or topic",
                        },
                        "id": {
                            "type": "string",
                            "required": "for UPDATE/DELETE",
                            "description": "Hint ID",
                        },
                        "hint": {
                            "type": "string",
                            "required": "for CREATE/UPDATE",
                            "description": "The hint text",
                        },
                    },
                },
            )

        method_upper = method.upper()

        if method_upper == "READ":
            category = args.get("category")
            key = args.get("key")
            hint_id = args.get("id")

            if hint_id:
                hint = self._hint_store.get_by_id(hint_id)
                return ToolResult(success=True, data={"hints": [hint] if hint else [], "count": 1 if hint else 0})
            elif category and key:
                hints = self._hint_store.read(category=category, key=key)
            elif category:
                hints = self._hint_store.read(category=category)
            else:
                hints = self._hint_store.read()

            return ToolResult(success=True, data={"hints": hints, "count": len(hints)})

        elif method_upper == "CREATE":
            category = args.get("category")
            key = args.get("key")
            hint_text = args.get("hint")

            if not category or not key or not hint_text:
                return ToolResult(success=False, error="CREATE requires category, key, and hint")

            hint = self._hint_store.create(category=category, key=key, hint=hint_text)
            return ToolResult(success=True, data={"hint": hint})

        elif method_upper == "UPDATE":
            hint_id = args.get("id")
            hint_text = args.get("hint")

            if not hint_id or not hint_text:
                return ToolResult(success=False, error="UPDATE requires id and hint")

            hint = self._hint_store.update(hint_id=hint_id, hint=hint_text)
            if not hint:
                return ToolResult(success=False, error=f"Hint {hint_id} not found")

            return ToolResult(success=True, data={"hint": hint})

        elif method_upper == "DELETE":
            hint_id = args.get("id")
            if not hint_id:
                return ToolResult(success=False, error="DELETE requires id")

            success = self._hint_store.delete(hint_id=hint_id)
            return ToolResult(success=success, data={"message": f"Deleted hint {hint_id}" if success else f"Hint {hint_id} not found"})

        else:
            return ToolResult(success=False, error=f"Unknown hints method: {method}")


# ── Gateway introspection ─────────────────────────────────────────
# Helpers for host applications (display layers, tool dispatchers)
# to detect when a tool call is a toolbox ``run`` that targets
# another tool, and unwrap it to the inner tool's identity.


GATEWAY_TOOL_NAME = "toolbox"


def is_available() -> bool:
    """True if the toolbox_gateway package is importable.

    Convenience for host applications that want to check availability
    without a try/except block.
    """
    try:
        import toolbox_gateway  # noqa: F401
        return True
    except ImportError:
        return False


def is_gateway_call(tool_name: str, args: dict | None) -> bool:
    """Return True if this tool call is a toolbox ``run`` targeting an inner tool.

    A gateway call has shape ``{command: "run", toolName: "X", args: {...}}``.
    Other toolbox commands (list, explain, hints) are NOT gateway calls —
    they should be displayed and dispatched as toolbox itself.
    """
    if tool_name != GATEWAY_TOOL_NAME or not args:
        return False
    return args.get("command") == "run" and bool(args.get("toolName"))


def unwrap_gateway_call(tool_name: str, args: dict) -> tuple[str, dict]:
    """If this is a gateway ``run`` call, return (inner_tool_name, inner_args).

    Otherwise return (tool_name, args) unchanged. Convenience for display
    and dispatch layers that want to delegate rendering/execution to the
    inner tool.
    """
    if is_gateway_call(tool_name, args):
        return args["toolName"], args.get("args") or {}
    return tool_name, args