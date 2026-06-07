"""MCP registry — discovery and routing for Model Context Protocol servers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class MCPServerInfo:
    """Metadata about a connected MCP server."""

    id: str
    name: str = ""
    use_when: str = ""  # Human-readable description of when to use this server
    priority: int = 0

    def list_tools(self) -> list[dict[str, Any]]:
        """List tools available on this server. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement list_tools()")

    def explain_tools(self, tool_names: list[str]) -> dict[str, Any]:
        """Get schema details for specific tools. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement explain_tools()")

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Execute a tool on this server. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement execute_tool()")


class MCPRegistry:
    """Registry for MCP servers.

    Register servers at init time or via register_server(). The toolbox
    routes `--mcp=serverId` commands through this registry.

    Usage::

        registry = MCPRegistry()
        registry.register_server(MyMCPServer(id="polygon", name="Polygon.io"))
        toolbox = Toolbox(tools=[...], mcp_registry=registry)
    """

    def __init__(self, servers: list[MCPServerInfo] | None = None) -> None:
        self._servers: dict[str, MCPServerInfo] = {}
        if servers:
            for s in servers:
                self._servers[s.id] = s

    def register_server(self, server: MCPServerInfo) -> None:
        """Register an MCP server."""
        self._servers[server.id] = server

    def unregister_server(self, server_id: str) -> None:
        """Unregister an MCP server."""
        self._servers.pop(server_id, None)

    def get_server(self, server_id: str) -> MCPServerInfo | None:
        """Look up a server by ID."""
        return self._servers.get(server_id)

    def list_servers(self) -> list[dict[str, Any]]:
        """List all registered servers with metadata."""
        return [
            {
                "id": s.id,
                "name": s.name,
                "use_when": s.use_when,
                "priority": s.priority,
            }
            for s in sorted(self._servers.values(), key=lambda s: s.priority, reverse=True)
        ]