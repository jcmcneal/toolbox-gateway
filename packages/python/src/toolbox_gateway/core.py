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


# Reserved command names that cannot be used as tool names via the run command
RESERVED_COMMAND_NAMES: set[str] = {cmd.value for cmd in ToolboxCommand}


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
        schema_format: str = "markdown",  # "markdown" (default) or "json" (raw JSON Schema)
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
        return cls(
            tools=_definitions_to_tools(definitions, dispatcher),
            hint_store=hint_store,
            schema_format=schema_format,
        )

    @classmethod
    def from_provider(
        cls,
        provider: Callable[[], list[dict]],
        dispatcher: Callable[[str, dict], Any],
        hint_store: Optional[HintStore] = None,
        schema_format: str = "markdown",
    ) -> "Toolbox":
        """Build a Toolbox where the tool list is fetched lazily from a provider.

        *provider* is a zero-arg callable returning the list of definition
        dicts (same shape as ``from_definitions``). It is called each time
        the gateway needs the current tool list — so adding/removing tools
        in the host application is reflected automatically.

        *dispatcher* routes execution back to the host.

        Use ``toolbox.refresh()`` to force re-read of the provider.
        """
        instance = cls(
            tools=_definitions_to_tools(provider(), dispatcher),
            hint_store=hint_store,
            schema_format=schema_format,
        )
        instance._provider = provider
        instance._dispatcher = dispatcher
        return instance

    def refresh(self) -> None:
        """Re-fetch the tool list from the provider. No-op if not a provider-built toolbox."""
        provider = getattr(self, "_provider", None)
        if provider is None:
            return
        self._tools = {t.name: t for t in _definitions_to_tools(provider(), self._dispatcher)}

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
                "(use --mcp=serverId for MCP tools, --detail=names|params|schema "
                "to control which fields each tool entry includes)\n"
                "- explain: Get schema docs for one or more tools "
                "(provide toolNames, use --mcp=serverId for MCP tools, "
                "--format=json to force raw JSON Schema)\n"
                "- run: Execute a tool (requires toolName and subject, "
                "use --mcp=serverId for MCP tools)\n"
                "- servers: List available MCP servers and their descriptions\n"
                "- hints: Manage universal hints for tool usage, gotchas, "
                "and MCP shortcuts (method: READ|CREATE|UPDATE|DELETE)\n\n"
                "The host controls the response format for list and explain via "
                "schema_format: 'json' (plain JSON), 'markdown' (fenced CSV/docs), "
                "or 'csv' (raw CSV with type hints). Default is 'markdown'.\n\n"
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
                    "detail": {
                        "type": "string",
                        "enum": ["names", "params", "schema"],
                        "description": (
                            "Per-entry fields for list: names (name+desc only), "
                            "params (add compact param hints, default), "
                            "schema (add full JSON Schema)"
                        ),
                    },
                    "toolNames": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tools to explain (for explain command, accepts multiple)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json"],
                        "description": "Force JSON output for explain, overriding schema_format",
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

    def handle_args(self, args: dict) -> ToolResult:
        """Like ``handle()`` but takes the raw LLM tool-call args dict.

        Convenience for host applications: forward the entire args dict
        here and the package routes the right command handler.

        The ``command`` key must be present; other keys are passed through
        to the appropriate handler. Unknown commands return an error.
        """
        if not args:
            return ToolResult(success=False, error="Missing command")
        command = args.get("command", "")
        if not command:
            return ToolResult(success=False, error="Missing command")
        forward = {k: v for k, v in args.items() if k != "command"}
        return self.handle(command=command, **forward)

    # ── List ──────────────────────────────────────────────────────────

    def _handle_list(
        self,
        *,
        detail: str | None = None,
        mcp: str | None = None,
        **_: Any,
    ) -> ToolResult:
        """Return the tool list in the host-configured schema_format.

        ``detail`` (LLM-controlled, default "params") controls which fields
        each tool entry includes:

        - ``"names"`` — just name + description
        - ``"params"`` (default) — name + description + compact param hint
        - ``"schema"`` — name + description + raw JSON Schema

        ``schema_format`` (host-configured at construction) controls the
        response envelope:

        - ``"json"`` — plain JSON dict: ``{"tools": [...], "count": N}``
        - ``"markdown"`` — fenced CSV table (just the text, no JSON wrapper)
        - ``"csv"`` — raw CSV with type-hinted header (just the text)
        """
        valid_details = {"names", "params", "schema"}
        if detail is not None and detail not in valid_details:
            return ToolResult(
                success=False,
                error=f"Invalid detail level: {detail}. Valid options: {', '.join(sorted(valid_details))}",
            )
        detail = detail or "params"

        if mcp:
            return self._list_mcp_tools(mcp, detail=detail)

        # Build the per-entry rows based on detail level
        rows = self._build_list_rows(detail)

        # Wrap in the host-configured schema_format envelope
        if self._schema_format == "markdown":
            from .schema import data_to_csv
            columns = self._list_columns(detail)
            text = data_to_csv(
                rows,
                columns=columns,
                fence_block="Available Tools",
            )
            return ToolResult(success=True, data=text)

        if self._schema_format == "csv":
            from .schema import data_to_csv_with_type_hints
            columns = self._list_columns(detail)
            text = data_to_csv_with_type_hints(
                rows,
                columns=columns,
                comment="Available Tools",
            )
            return ToolResult(success=True, data=text)

        # schema_format == "json" (or any unrecognized value falls through to JSON)
        return ToolResult(success=True, data={"tools": rows, "count": len(rows)})

    def _build_list_rows(self, detail: str) -> list[dict[str, Any]]:
        """Build the per-entry dicts for a list response."""
        from .schema import schema_to_compact_params
        rows: list[dict[str, Any]] = []
        for name, t in self._tools.items():
            if t.is_hidden:
                continue
            entry: dict[str, Any] = {"name": name, "description": t.description}
            if detail == "schema":
                entry["schema"] = t.schema
            elif detail == "params":
                entry["params"] = schema_to_compact_params(t.schema)
            # detail == "names": just name + description
            rows.append(entry)
        return rows

    @staticmethod
    def _list_columns(detail: str) -> list[str]:
        """Return the column order for tabular (markdown/csv) list output."""
        if detail == "schema":
            return ["name", "description", "schema"]
        if detail == "params":
            return ["name", "description", "params"]
        return ["name", "description"]

    def _list_mcp_tools(self, server_id: str, detail: str = "params") -> ToolResult:
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

    def _handle_explain(
        self,
        *,
        toolNames: list[str] | None = None,
        format: str | None = None,
        mcp: str | None = None,
        **_: Any,
    ) -> ToolResult:
        """Return schema details for one or more tools.

        ``format`` (LLM-controlled, ``"json"``) overrides the host's
        ``schema_format`` to force raw JSON Schema output.

        Response envelope depends on ``schema_format`` (or ``format``
        override):

        - ``"json"`` — ``{"explanations": {name: {description, schema}}}``
        - ``"markdown"`` — raw markdown docs (one per tool, no wrapper)
        - ``"csv"`` — raw CSV parameter tables (one per tool, no wrapper)
        """
        names = toolNames or []
        if not names:
            return ToolResult(
                success=False,
                error="explain requires at least one tool name in toolNames",
            )

        if mcp:
            return self._explain_mcp_tools(names, mcp)

        # Per-call format override: 'json' forces raw schema regardless of default
        effective_format = "json" if format == "json" else self._schema_format

        explanations: dict[str, str | dict[str, Any]] = {}
        not_found: list[str] = []

        for name in names:
            tool = self._tools.get(name)
            if tool:
                if effective_format == "markdown":
                    from .schema import schema_to_markdown
                    explanations[name] = schema_to_markdown(
                        tool.schema,
                        title=name,
                        description=tool.description,
                    )
                elif effective_format == "csv":
                    from .schema import schema_to_csv
                    explanations[name] = schema_to_csv(tool.schema, comment=name)
                else:
                    explanations[name] = {
                        "description": tool.description,
                        "schema": tool.schema,
                    }
            else:
                not_found.append(name)

        if not explanations:
            return ToolResult(
                success=False,
                error=f"Tools not found: {', '.join(not_found)}",
            )

        if effective_format in ("markdown", "csv"):
            sep = "\n\n" if effective_format == "markdown" else "\n"
            text = sep.join(explanations.values())
            if not_found:
                text += f"\n\n# Not found: {', '.join(not_found)}"
            return ToolResult(success=True, data=text)

        # JSON envelope
        result_data: dict[str, Any] = {"explanations": explanations}
        if not_found:
            result_data["not_found"] = not_found
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
        if toolName in RESERVED_COMMAND_NAMES:
            return ToolResult(
                success=False,
                error=f"'{toolName}' is a toolbox command, not a tool to run. "
                      f"Call toolbox with command='{toolName}' instead.",
            )
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


def _definitions_to_tools(
    definitions: list[dict],
    dispatcher: Callable[[str, dict], Any],
) -> list["Tool"]:
    """Convert definition dicts to ``Tool`` objects wired to *dispatcher*."""
    return [
        Tool(
            name=d["name"],
            description=d.get("description", ""),
            schema=d.get("schema", {}),
            execute=lambda args, _name=d["name"], **kw: dispatcher(_name, args),
        )
        for d in definitions
    ]


# ── Tool definitions (for the LLM) ───────────────────────────────
# Schema for the gateway tool — kept in one place so the prompt
# text and parameter definitions stay in sync.


def _toolbox_definition() -> dict[str, Any]:
    """Return the canonical toolbox schema. See ``Toolbox.get_tool_definition``."""
    return Toolbox.get_tool_definition()


# ── Filter helpers ───────────────────────────────────────────────
# Convenience for host apps that want to collapse N tool definitions
# into a single gateway definition (the "shoebox" pattern).


def filter_to_gateway_only(
    tools: list[dict],
    gateway_name: str = GATEWAY_TOOL_NAME,
) -> list[dict]:
    """Return only the gateway tool definition from a list of tool defs.

    Each input dict is expected to have a ``"function": {"name": ...}``
    or top-level ``"name"`` key. Pass OpenAI-style function-calling
    tool defs (with ``"function": {"name": ...}`` wrapper) or plain
    toolbox-style defs and it figures out which.

    Returns the gateway definition if present, else an empty list.
    Use this to drop N tool schemas from a system prompt when the
    gateway is enabled.
    """
    out = []
    for t in tools:
        name = t.get("function", t).get("name")
        if name == gateway_name:
            out.append(t)
    return out


def should_collapse_to_gateway(
    available_tool_names: set[str],
    gateway_name: str = GATEWAY_TOOL_NAME,
) -> bool:
    """True if the gateway is in the available set AND the package is installed.

    Use this to decide whether to drop all other tool schemas from the
    prompt and replace them with the single gateway definition.
    """
    return gateway_name in available_tool_names and is_available()


# ── Display / spinner helpers ────────────────────────────────────
# Host apps that render a spinner or completion line per tool call
# can use these to apply gateway-aware formatting consistently.


def spinner_label(tool_name: str, args: dict | None) -> str | None:
    """Return a short label for a tool call's spinner, or None for default.

    For gateway calls (``toolbox list`` etc.), returns a short label
    like ``"toolbox"`` to suppress verbose "preparing toolbox…" messages.
    """
    if tool_name == GATEWAY_TOOL_NAME and args:
        command = args.get("command", "")
        if command in ("list", "explain", "servers", "hints"):
            return "toolbox"
    return None


def unwrap_with_subject(
    tool_name: str,
    args: dict,
) -> tuple[str, dict, str]:
    """Unwrap a gateway call, returning (inner_name, inner_args, subject).

    The subject is the toolbox annotation (the LLM's brief intent
    description). For non-gateway calls, returns the input unchanged
    and an empty subject.

    The subject is also embedded into the returned ``inner_args`` under
    the key ``"_subject"`` so display layers can pass the result
    through unchanged. The top-level ``subject`` return is for
    callers that want to handle the annotation separately.

    Convenience for display layers: the host's renderer can call
    this once, then render the inner tool with the args dict as-is
    (the ``_subject`` key is then a no-op for non-display code).
    """
    inner_name, inner_args = unwrap_gateway_call(tool_name, args)
    subject = ""
    if inner_name != tool_name and (args or {}).get("subject"):
        subject = args["subject"]
        inner_args = dict(inner_args or {})
        inner_args["_subject"] = subject
    return inner_name, inner_args, subject


def preview_for_command(command: str, args: dict | None) -> str | None:
    """Return the *full* preview string for a non-``run`` gateway command.

    Use this when you need a single self-contained preview string
    (e.g. for ``build_tool_preview``). For cute-message formatting,
    use ``label_for_command()`` instead so the verb and detail can
    be aligned separately.

    Examples:
    - list → "list tools"
    - hints READ → "read hints"
    - explain terminal,read_file → "explain terminal, read_file"
    - servers → "list servers"
    """
    args = args or {}
    if command == "list":
        return "list tools"
    if command == "explain":
        names = args.get("toolNames") or ([args.get("toolName", "")] if args.get("toolName") else [])
        if names:
            joined = ", ".join(names) if isinstance(names, list) else str(names)
            return f"explain {joined}"
        return "explain"
    if command == "hints":
        method = (args.get("method") or "READ").upper()
        verb = "browse" if method == "READ" else method.lower()
        return f"{verb} hints"
    if command == "servers":
        return "list servers"
    return command or None


def label_for_command(command: str, args: dict | None) -> str:
    """Return a short verb (3-7 chars) for a non-``run`` gateway command.

    Used by display layers to format cute-tool-message lines.
    """
    args = args or {}
    if command == "list":
        return "list"
    if command == "explain":
        return "explain"
    if command == "hints":
        method = (args.get("method") or "READ").upper()
        return "browse" if method == "READ" else method.lower()
    if command == "servers":
        return "servers"
    return (command or "")[:9]


def detail_for_command(command: str, args: dict | None) -> str:
    """Return the *detail* (after the verb) for a non-``run`` gateway command.

    Pair with ``label_for_command()`` to assemble aligned cute-message
    lines. For self-contained preview strings, use ``preview_for_command()``.

    Examples:
    - list → "tools"
    - hints → "hints"
    - explain terminal,read_file → "terminal, read_file"
    - servers → "servers"
    """
    args = args or {}
    if command == "list":
        return "tools"
    if command == "explain":
        names = args.get("toolNames") or ([args.get("toolName", "")] if args.get("toolName") else [])
        if names:
            return ", ".join(names) if isinstance(names, list) else str(names)
        return ""
    if command == "hints":
        return "hints"
    if command == "servers":
        return "servers"
    return command or ""


# ── Toolset definition (Hermes-style) ────────────────────────────
# Standard "toolset" descriptor for hosts that group tools by
# use-case. The toolbox toolset contains only the gateway tool.


TOOLSET_DEFINITION: dict[str, Any] = {
    "name": GATEWAY_TOOL_NAME,
    "description": (
        "Toolbox gateway — collapse niche tools into a single discovery tool. "
        "The LLM uses toolbox list/explain/run to find and invoke infrequently-needed "
        "tools instead of bloating the system prompt with all their schemas."
    ),
    "tools": [GATEWAY_TOOL_NAME],
}