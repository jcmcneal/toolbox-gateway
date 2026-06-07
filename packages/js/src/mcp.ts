/**
 * MCP Registry — discovery and routing for Model Context Protocol servers.
 *
 * Usage::
 *
 *     const registry = new MCPRegistry();
 *     registry.registerServer(new MyMCPServer('polygon', 'Polygon.io', 'Market data'));
 *
 *     const toolbox = new Toolbox(tools, { mcpRegistry: registry });
 */

import type { MCPServerInfo } from './index.js';

export class MCPRegistry {
  private servers: Map<string, MCPServerInfo> = new Map();

  constructor(servers?: MCPServerInfo[]) {
    if (servers) {
      for (const s of servers) {
        this.servers.set(s.id, s);
      }
    }
  }

  /** Register an MCP server instance. */
  registerServer(server: MCPServerInfo): void {
    this.servers.set(server.id, server);
  }

  /** Unregister an MCP server by ID. */
  unregisterServer(serverId: string): void {
    this.servers.delete(serverId);
  }

  /** Look up a server by ID. */
  getServer(serverId: string): MCPServerInfo | undefined {
    return this.servers.get(serverId);
  }

  /** List all registered servers with metadata, sorted by priority descending. */
  listServers(): { id: string; name: string; use_when: string; priority: number }[] {
    return Array.from(this.servers.values())
      .sort((a, b) => b.priority - a.priority)
      .map((s) => ({
        id: s.id,
        name: s.name,
        use_when: s.use_when,
        priority: s.priority,
      }));
  }
}
