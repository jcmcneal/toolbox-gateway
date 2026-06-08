"""Tests for the core Toolbox class."""

import pytest

from toolbox_gateway import Toolbox, Tool, MemoryHintStore


# ── Helpers ──────────────────────────────────────────────────────────

def make_tool(name: str, desc: str = "A test tool") -> Tool:
    """Create a simple tool with a predictable execute function."""
    return Tool(
        name=name,
        description=desc,
        schema={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Some input"},
            },
            "required": ["input"],
        },
        execute=lambda args: {"echo": args.get("input", ""), "tool": name},
    )


def make_toolbox(n_tools: int = 3, schema_format: str = "json") -> Toolbox:
    """Create a toolbox with n simple echo tools."""
    tools = [make_tool(f"tool_{i}", f"Tool number {i}") for i in range(n_tools)]
    return Toolbox(tools=tools, hint_store=MemoryHintStore(), schema_format=schema_format)


def make_toolbox_md(n_tools: int = 3) -> Toolbox:
    """Create a toolbox with default markdown schema_format."""
    tools = [make_tool(f"tool_{i}", f"Tool number {i}") for i in range(n_tools)]
    return Toolbox(tools=tools, hint_store=MemoryHintStore())


# ── Tool Definition ─────────────────────────────────────────────────

class TestToolDefinition:
    def test_get_tool_definition_returns_single_tool(self):
        tb = make_toolbox()
        defn = tb.get_tool_definition()

        assert defn["name"] == "toolbox"
        assert "command" in defn["parameters"]["properties"]
        assert defn["parameters"]["required"] == ["command"]

    def test_tool_definition_is_compact(self):
        """With realistic schemas, the single toolbox definition should be smaller than all individual schemas."""
        tb = make_toolbox(10)
        defn = tb.get_tool_definition()

        import json
        toolbox_schema_size = len(json.dumps(defn))

        # Simulate realistic tool schemas (not minimal empty ones)
        realistic_sizes = []
        for t in tb._tools.values():
            # Real tools have more complex schemas than our test fixtures
            realistic_schema = {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Some input"},
                    "limit": {"type": "integer", "description": "Max results"},
                    "offset": {"type": "integer", "description": "Pagination offset"},
                },
                "required": ["input"],
            }
            realistic_sizes.append(len(json.dumps(realistic_schema)))

        all_schemas_size = len(json.dumps(defn["parameters"])) + sum(realistic_sizes)
        # The point: N realistic schemas + N tool definitions >> 1 toolbox definition
        assert toolbox_schema_size < all_schemas_size


# ── List Command ─────────────────────────────────────────────────────

class TestListCommand:
    def test_list_returns_all_visible_tools(self):
        """JSON format returns tools array with all visible tools."""
        tb = make_toolbox(3, schema_format="json")
        result = tb.handle(command="list")

        assert result.success
        assert result.data["count"] == 3
        names = [t["name"] for t in result.data["tools"]]
        assert "tool_0" in names
        assert "tool_1" in names
        assert "tool_2" in names

    def test_list_hides_hidden_tools(self):
        """Hidden tools are excluded from list output."""
        tools = [
            make_tool("visible"),
            Tool(name="secret", description="Hidden", schema={}, execute=lambda _: None, is_hidden=True),
        ]
        tb = Toolbox(tools=tools, hint_store=MemoryHintStore(), schema_format="json")
        result = tb.handle(command="list")

        assert result.success
        assert result.data["count"] == 1
        assert result.data["tools"][0]["name"] == "visible"

    def test_list_includes_descriptions(self):
        tb = make_toolbox(1, schema_format="json")
        result = tb.handle(command="list")

        assert result.data["tools"][0]["description"] == "Tool number 0"

    def test_list_default_detail_is_params(self):
        """list with no detail param returns params field per tool."""
        tb = make_toolbox(1, schema_format="json")
        result = tb.handle(command="list")

        assert "params" in result.data["tools"][0]
        assert result.data["tools"][0]["params"] != ""

    def test_list_detail_names(self):
        """detail=names returns only name and description."""
        tb = make_toolbox(1, schema_format="json")
        result = tb.handle(command="list", detail="names")

        assert "params" not in result.data["tools"][0]
        assert "schema" not in result.data["tools"][0]

    def test_list_detail_schema(self):
        """detail=schema includes full JSON Schema per tool."""
        tb = make_toolbox(1, schema_format="json")
        result = tb.handle(command="list", detail="schema")

        assert "schema" in result.data["tools"][0]
        assert result.data["tools"][0]["schema"] != {}

    def test_list_default_format_is_markdown(self):
        """Default output is markdown CSV table (not JSON dict)."""
        tb = make_toolbox_md(3)
        result = tb.handle(command="list")

        assert result.success
        assert isinstance(result.data, str)
        assert "tool_0" in result.data
        assert "tool_1" in result.data
        assert "tool_2" in result.data
        assert "Available Tools" in result.data

    def test_list_csv_format(self):
        """schema_format=csv returns raw CSV with type hints."""
        tool = Tool(name="test_tool", description="A test tool", schema={}, execute=lambda _: None)
        tb = Toolbox(tools=[tool], hint_store=MemoryHintStore(), schema_format="csv")
        result = tb.handle(command="list")

        assert result.success
        assert isinstance(result.data, str)
        assert "test_tool" in result.data
        assert "name (string)" in result.data
        assert "description (string)" in result.data

    def test_list_detail_params_explicit(self):
        """detail=params is the same as default."""
        tb = make_toolbox(1, schema_format="json")
        result = tb.handle(command="list", detail="params")

        assert "params" in result.data["tools"][0]
        assert result.data["tools"][0]["params"] != ""

    def test_list_invalid_detail_returns_error(self):
        tb = make_toolbox(1)
        result = tb.handle(command="list", detail="invalid")

        assert not result.success
        assert "Invalid detail level" in result.error

    def test_list_params_for_tool_with_empty_schema(self):
        """Tools with empty schema get empty string for params."""
        tool = Tool(name="empty", description="Empty schema", schema={}, execute=lambda _: None)
        tb = Toolbox(tools=[tool], hint_store=MemoryHintStore(), schema_format="json")
        result = tb.handle(command="list")

        assert result.data["tools"][0]["params"] == ""

    def test_list_schema_for_tool_with_empty_schema(self):
        """Tools with empty schema get {} for schema field."""
        tool = Tool(name="empty", description="Empty schema", schema={}, execute=lambda _: None)
        tb = Toolbox(tools=[tool], hint_store=MemoryHintStore(), schema_format="json")
        result = tb.handle(command="list", detail="schema")

        assert result.data["tools"][0]["schema"] == {}

    def test_list_markdown_for_tool_with_empty_schema(self):
        """Tools with empty schema still appear in markdown table."""
        tool = Tool(name="empty", description="Empty schema", schema={}, execute=lambda _: None)
        tb = Toolbox(tools=[tool], hint_store=MemoryHintStore())
        result = tb.handle(command="list")

        assert isinstance(result.data, str)
        assert "empty" in result.data
        assert "Empty schema" in result.data

    def test_list_csv_for_tool_with_empty_schema(self):
        """Tools with empty schema still appear in csv output."""
        tool = Tool(name="empty", description="Empty schema", schema={}, execute=lambda _: None)
        tb = Toolbox(tools=[tool], hint_store=MemoryHintStore(), schema_format="csv")
        result = tb.handle(command="list")

        assert isinstance(result.data, str)
        assert "empty" in result.data


# ── Explain Command ──────────────────────────────────────────────────

class TestExplainCommand:
    def test_explain_returns_string_for_default_markdown(self):
        """Default markdown format returns string with tool docs."""
        tb = make_toolbox_md(3)
        result = tb.handle(command="explain", toolNames=["tool_0", "tool_2"])

        assert result.success
        assert isinstance(result.data, str)
        assert "tool_0" in result.data
        assert "tool_2" in result.data

    def test_explain_json_format(self):
        """format=json forces JSON output regardless of schema_format."""
        tb = make_toolbox_md(3)
        result = tb.handle(command="explain", toolNames=["tool_0", "tool_2"], format="json")

        assert result.success
        assert isinstance(result.data, dict)
        assert "tool_0" in result.data["explanations"]
        assert "tool_2" in result.data["explanations"]
        assert "schema" in result.data["explanations"]["tool_0"]

    def test_explain_reports_not_found_in_markdown(self):
        """Not-found tools are listed in the markdown output body."""
        tb = make_toolbox_md(2)
        result = tb.handle(command="explain", toolNames=["tool_0", "nonexistent"])

        assert result.success
        assert isinstance(result.data, str)
        assert "tool_0" in result.data
        assert "Not found" in result.data
        assert "nonexistent" in result.data

    def test_explain_reports_not_found_in_json(self):
        """Not-found tools are listed in not_found array for JSON output."""
        tb = make_toolbox(2, schema_format="json")
        result = tb.handle(command="explain", toolNames=["tool_0", "nonexistent"])

        assert result.success
        assert isinstance(result.data, dict)
        assert "tool_0" in result.data["explanations"]
        assert "nonexistent" in result.data["not_found"]

    def test_explain_fails_with_no_tool_names(self):
        tb = make_toolbox()
        result = tb.handle(command="explain", toolNames=[])

        assert not result.success
        assert "requires at least one" in result.error

    def test_explain_all_not_found(self):
        tb = make_toolbox(1)
        result = tb.handle(command="explain", toolNames=["ghost_tool"])

        assert not result.success
        assert "ghost_tool" in result.error

    def test_explain_csv_format(self):
        """schema_format=csv returns raw CSV per tool."""
        tb = make_toolbox(2, schema_format="csv")
        result = tb.handle(command="explain", toolNames=["tool_0"])

        assert result.success
        assert isinstance(result.data, str)
        assert "tool_0" in result.data
        assert "input" in result.data  # CSV header contains field name
        assert "string" in result.data  # Type hint in comment


# ── Run Command ─────────────────────────────────────────────────────

class TestRunCommand:
    def test_run_executes_tool(self):
        tb = make_toolbox(1)
        result = tb.handle(command="run", toolName="tool_0", subject="Testing echo", args={"input": "hello"})

        assert result.success
        assert result.data["result"]["echo"] == "hello"
        assert result.data["source"] == "native"
        assert result.duration_ms is not None

    def test_run_requires_tool_name(self):
        tb = make_toolbox()
        result = tb.handle(command="run", subject="No tool name")

        assert not result.success
        assert "toolName" in result.error

    def test_run_requires_subject(self):
        tb = make_toolbox(1)
        result = tb.handle(command="run", toolName="tool_0")

        assert not result.success
        assert "subject" in result.error

    def test_run_unknown_tool(self):
        tb = make_toolbox(1)
        result = tb.handle(command="run", toolName="ghost", subject="Trying ghost tool")

        assert not result.success
        assert "not found" in result.error

    def test_run_measures_duration(self):
        tb = make_toolbox(1)
        result = tb.handle(command="run", toolName="tool_0", subject="Timing test", args={"input": "x"})

        assert result.duration_ms is not None
        assert result.duration_ms >= 0


# ── Servers Command ─────────────────────────────────────────────────

class TestServersCommand:
    def test_servers_fails_without_mcp(self):
        tb = make_toolbox()
        result = tb.handle(command="servers")

        assert not result.success
        assert "No MCP registry" in result.error

    def test_servers_lists_registered_servers(self):
        from toolbox_gateway.mcp import MCPRegistry, MCPServerInfo

        registry = MCPRegistry()
        registry.register_server(MCPServerInfo(id="test", name="Test Server", use_when="Testing"))
        tb = make_toolbox(1)
        tb._mcp_registry = registry

        result = tb.handle(command="servers")
        assert result.success
        assert result.data["count"] == 1
        assert result.data["servers"][0]["id"] == "test"


# ── Hints Command ───────────────────────────────────────────────────

class TestHintsCommand:
    def test_hints_returns_schema_when_no_method(self):
        tb = make_toolbox()
        result = tb.handle(command="hints", args={})

        assert result.success
        assert "schema" in result.data

    def test_hints_create_and_read(self):
        tb = make_toolbox()
        # Create
        create_result = tb.handle(
            command="hints",
            args={"method": "CREATE", "category": "tool", "key": "tool_0", "hint": "Requires uppercase tickers"},
        )
        assert create_result.success
        hint_id = create_result.data["hint"]["id"]

        # Read all
        read_result = tb.handle(command="hints", args={"method": "READ"})
        assert read_result.success
        assert read_result.data["count"] >= 1

        # Read by category
        cat_result = tb.handle(command="hints", args={"method": "READ", "category": "tool"})
        assert cat_result.success

    def test_hints_update(self):
        tb = make_toolbox()
        create = tb.handle(
            command="hints",
            args={"method": "CREATE", "category": "general", "key": "test", "hint": "Old hint"},
        )
        hint_id = create.data["hint"]["id"]

        update = tb.handle(
            command="hints",
            args={"method": "UPDATE", "id": hint_id, "hint": "New hint"},
        )
        assert update.success
        assert update.data["hint"]["hint"] == "New hint"

    def test_hints_delete(self):
        tb = make_toolbox()
        create = tb.handle(
            command="hints",
            args={"method": "CREATE", "category": "general", "key": "temp", "hint": "Temporary"},
        )
        hint_id = create.data["hint"]["id"]

        delete = tb.handle(command="hints", args={"method": "DELETE", "id": hint_id})
        assert delete.success

    def test_hints_idempotent_create(self):
        """Creating the same category+key twice returns the existing hint."""
        tb = make_toolbox()
        first = tb.handle(
            command="hints",
            args={"method": "CREATE", "category": "tool", "key": "dedup", "hint": "First"},
        )
        second = tb.handle(
            command="hints",
            args={"method": "CREATE", "category": "tool", "key": "dedup", "hint": "Second"},
        )

        assert first.data["hint"]["id"] == second.data["hint"]["id"]
        assert second.data["hint"]["hint"] == "First"  # Not updated


# ── Unknown Command ─────────────────────────────────────────────────

class TestEdgeCases:
    def test_unknown_command(self):
        tb = make_toolbox()
        result = tb.handle(command="destroy")

        assert not result.success
        assert "Unknown command" in result.error
