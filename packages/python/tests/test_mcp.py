"""Tests for the MCP registry."""

import pytest

from toolbox.mcp import MCPRegistry, MCPServerInfo


class SimpleMCPServer(MCPServerInfo):
    """Test MCP server with tool discovery."""

    def __init__(self, tools: list[dict] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._tools = tools or []

    def list_tools(self):
        return self._tools

    def explain_tools(self, tool_names: list[str]):
        found = {t["name"]: t for t in self._tools if t["name"] in tool_names}
        not_found = [n for n in tool_names if n not in found]
        result = {"explanations": found}
        if not_found:
            result["not_found"] = not_found
        return result

    def execute_tool(self, tool_name: str, args: dict):
        return {"result": f"executed {tool_name}", "args": args}


class TestMCPRegistry:
    def test_register_and_list_servers(self):
        registry = MCPRegistry()
        registry.register_server(SimpleMCPServer(id="test", name="Test", use_when="Testing"))

        servers = registry.list_servers()
        assert len(servers) == 1
        assert servers[0]["id"] == "test"

    def test_unregister_server(self):
        registry = MCPRegistry()
        registry.register_server(SimpleMCPServer(id="test", name="Test", use_when="Testing"))
        registry.unregister_server("test")

        assert registry.get_server("test") is None

    def test_get_server(self):
        registry = MCPRegistry()
        registry.register_server(SimpleMCPServer(id="polygon", name="Polygon.io", use_when="Market data"))

        server = registry.get_server("polygon")
        assert server is not None
        assert server.name == "Polygon.io"

    def test_list_servers_sorted_by_priority(self):
        registry = MCPRegistry()
        registry.register_server(SimpleMCPServer(id="low", name="Low", priority=1, use_when=""))
        registry.register_server(SimpleMCPServer(id="high", name="High", priority=10, use_when=""))

        servers = registry.list_servers()
        assert servers[0]["id"] == "high"
        assert servers[1]["id"] == "low"

    def test_mcp_list_tools_via_toolbox(self):
        from toolbox import Toolbox, Tool

        registry = MCPRegistry()
        registry.register_server(SimpleMCPServer(
            id="test",
            name="Test",
            use_when="Testing",
            tools=[{"name": "mcp_tool", "description": "An MCP tool"}],
        ))

        tb = Toolbox(tools=[Tool(name="native", description="Native tool", schema={}, execute=lambda _: None)], mcp_registry=registry)
        result = tb.handle(command="list", mcp="test")

        assert result.success
        assert result.data["count"] == 1
        assert result.data["tools"][0]["name"] == "mcp_tool"

    def test_mcp_run_via_toolbox(self):
        from toolbox import Toolbox, Tool

        registry = MCPRegistry()
        registry.register_server(SimpleMCPServer(id="test", name="Test", use_when="Testing"))

        tb = Toolbox(tools=[Tool(name="native", description="Native", schema={}, execute=lambda _: None)], mcp_registry=registry)
        result = tb.handle(command="run", toolName="some_tool", subject="Testing MCP", args={"input": "hello"}, mcp="test")

        assert result.success
        assert result.data["source"] == "mcp"

    def test_mcp_list_fails_without_registry(self):
        from toolbox import Toolbox, Tool

        tb = Toolbox(tools=[Tool(name="t", description="T", schema={}, execute=lambda _: None)])
        result = tb.handle(command="list", mcp="nonexistent")

        assert not result.success