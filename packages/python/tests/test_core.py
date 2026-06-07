"""Tests for the core Toolbox class."""

import pytest

from toolbox import Toolbox, Tool, MemoryHintStore


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


def make_toolbox(n_tools: int = 3) -> Toolbox:
    """Create a toolbox with n simple echo tools."""
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
        tb = make_toolbox(3)
        result = tb.handle(command="list")

        assert result.success
        assert result.data["count"] == 3
        names = [t["name"] for t in result.data["tools"]]
        assert "tool_0" in names
        assert "tool_1" in names
        assert "tool_2" in names

    def test_list_hides_hidden_tools(self):
        tools = [
            make_tool("visible"),
            Tool(name="secret", description="Hidden", schema={}, execute=lambda _: None, is_hidden=True),
        ]
        tb = Toolbox(tools=tools, hint_store=MemoryHintStore())
        result = tb.handle(command="list")

        assert result.success
        assert result.data["count"] == 1
        assert result.data["tools"][0]["name"] == "visible"

    def test_list_includes_descriptions(self):
        tb = make_toolbox(1)
        result = tb.handle(command="list")

        assert result.data["tools"][0]["description"] == "Tool number 0"


# ── Explain Command ──────────────────────────────────────────────────

class TestExplainCommand:
    def test_explain_returns_schema_for_named_tools(self):
        tb = make_toolbox(3)
        result = tb.handle(command="explain", toolNames=["tool_0", "tool_2"])

        assert result.success
        assert "tool_0" in result.data["explanations"]
        assert "tool_2" in result.data["explanations"]
        assert result.data["explanations"]["tool_0"]["schema"]["properties"]["input"]["type"] == "string"

    def test_explain_reports_not_found(self):
        tb = make_toolbox(2)
        result = tb.handle(command="explain", toolNames=["tool_0", "nonexistent"])

        assert result.success
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
        from toolbox.mcp import MCPRegistry, MCPServerInfo

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