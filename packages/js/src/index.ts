/**
 * Tool Gateway (Toolbox) — JavaScript implementation
 *
 * Single-tool gateway pattern for LLM agents.
 * Collapses N tool schemas into 1 gateway with lazy discovery.
 *
 * Protocol contract: see ../../fixtures/ for shared test fixtures.
 */

// ── Re-exports ──────────────────────────────────────────────────────

export { schemaToCsv, schemaToMarkdown, dataToCsv, dataToCsvWithTypeHints, schemaToCompactParams } from "./schema.js";
export { SQLiteHintStore } from "./sqlite-store.js";
export { MCPRegistry } from "./mcp.js";

// ── Local imports (needed by Toolbox implementation) ────────────────────

import { schemaToMarkdown as _schemaToMarkdown, dataToCsv as _dataToCsv, dataToCsvWithTypeHints as _dataToCsvWithTypeHints, schemaToCsv as _schemaToCsv, schemaToCompactParams } from "./schema.js";

// ── Types ─────────────────────────────────────────────────────────────

export interface ToolInput {
  name: string;
  description: string;
  schema: Record<string, unknown>;
  execute: (args: Record<string, unknown>) => unknown | Promise<unknown>;
  isHidden?: boolean;
}

export type ToolboxCommand = 'list' | 'explain' | 'run' | 'servers' | 'hints';

export interface ToolResult {
  success: boolean;
  data?: unknown;
  error?: string;
  duration_ms?: number;
}

export interface Hint {
  id: string;
  category: 'tool' | 'mcp-server' | 'mcp-tool' | 'general';
  key: string;
  hint: string;
  created_at: string;
  updated_at: string;
}

export interface HintStore {
  read(params?: { category?: string; key?: string }): Hint[];
  getById(hintId: string): Hint | undefined;
  create(params: { category: string; key: string; hint: string }): Hint;
  update(params: { hintId: string; hint: string }): Hint | undefined;
  delete(params: { hintId: string }): boolean;
}

export interface MCPServerInfo {
  readonly id: string;
  readonly name: string;
  readonly use_when: string;
  readonly priority: number;
  listTools(): Record<string, unknown>[];
  explainTools(toolNames: string[]): Record<string, unknown>;
  executeTool(toolName: string, args: Record<string, unknown>): unknown;
}

export interface MCPRegistryLike {
  registerServer(server: MCPServerInfo): void;
  unregisterServer(serverId: string): void;
  getServer(serverId: string): MCPServerInfo | undefined;
  listServers(): { id: string; name: string; use_when: string; priority: number }[];
}

// ── Gateway Tool Schema ───────────────────────────────────────────────

// Contract: see fixtures/run.json, fixtures/explain.json, fixtures/list.json

export const TOOLBOX_SCHEMA = {
  name: 'toolbox',
  description: `CLI-style gateway for all tools.

Commands:
- list: Show all available tools with descriptions (use --mcp=serverId for MCP tools, --detail=names|params|schema for per-entry fields)
- explain: Get schema docs for one or more tools (provide toolNames, use --mcp=serverId for MCP tools, --format=json for raw JSON Schema)
- run: Execute a tool (requires toolName and subject, use --mcp=serverId for MCP tools)
- servers: List available MCP servers and their descriptions
- hints: Manage universal hints for tool usage, gotchas, and MCP shortcuts (method: READ|CREATE|UPDATE|DELETE)

The host controls the response format for list and explain via schema_format: 'json' (plain JSON), 'markdown' (fenced CSV/docs), or 'csv' (raw CSV with type hints). Default is 'markdown'.

Always provide a "subject" when using "run" to explain your intent.`,
  parameters: {
    type: 'object',
    properties: {
      command: {
        type: 'string',
        enum: ['list', 'explain', 'run', 'servers', 'hints'],
        description: 'list | explain | run | servers | hints',
      },
      detail: {
        type: 'string',
        enum: ['names', 'params', 'schema'],
        description: 'Per-entry fields for list: names (name+desc only), params (add compact param hints, default), schema (add full JSON Schema)',
      },
      toolNames: {
        type: 'array',
        items: { type: 'string' },
        description: 'Tools to explain (for explain command, accepts multiple)',
      },
      format: {
        type: 'string',
        enum: ['json'],
        description: 'Force JSON output for explain, overriding schema_format',
      },
      toolName: {
        type: 'string',
        description: 'Tool to run (for run command)',
      },
      subject: {
        type: 'string',
        minLength: 5,
        maxLength: 80,
        description:
          'One-liner description of what you are doing. No more than 10 words. Do not reveal internal tool names or how it is handled internally.',
      },
      args: {
        type: 'object',
        description: 'Tool arguments (for run command)',
      },
      mcp: {
        type: 'string',
        description: 'MCP server ID to route command to (required for MCP tools)',
      },
    },
    required: ['command'],
  },
};

// ── Toolbox Implementation ────────────────────────────────────────────

export class Toolbox {
  private tools: Map<string, ToolInput>;
  private hintStore: HintStore;
  private mcpRegistry: MCPRegistryLike | null;
  private schemaFormat: 'json' | 'markdown' | 'csv';

  constructor(
    tools: ToolInput[],
    opts?: {
      hintStore?: HintStore;
      mcpRegistry?: MCPRegistryLike;
      schemaFormat?: 'json' | 'markdown' | 'csv';
    },
  ) {
    this.tools = new Map(tools.map((t) => [t.name, t]));
    this.hintStore = opts?.hintStore ?? new MemoryHintStore();
    this.mcpRegistry = opts?.mcpRegistry ?? null;
    this.schemaFormat = opts?.schemaFormat ?? 'markdown';
  }

  getToolDefinition(): Record<string, unknown> {
    return TOOLBOX_SCHEMA;
  }

  async handle(command: string, params: Record<string, unknown> = {}): Promise<ToolResult> {
    const start = Date.now();
    try {
      switch (command) {
        case 'list':
          return this.handleList(params);
        case 'explain':
          return this.handleExplain(params);
        case 'run':
          return this.handleRun(params, start);
        case 'servers':
          return this.handleServers();
        case 'hints':
          return this.handleHints(params);
        default:
          return { success: false, error: `Unknown command: ${command}` };
      }
    } catch (e) {
      return { success: false, error: String(e) };
    }
  }

  private handleList(params: Record<string, unknown>): ToolResult {
    const validDetails = ["names", "params", "schema"];
    const detail = (params.detail as string) ?? "params";

    if (params.detail !== undefined && !validDetails.includes(detail)) {
      return { success: false, error: `Invalid detail level: ${detail}. Valid options: ${validDetails.join(", ")}` };
    }

    // MCP routing
    if (params.mcp) {
      return this.listMcpTools(params.mcp as string, detail);
    }

    // Build per-entry rows based on detail level
    const rows = this.buildListRows(detail);

    // Wrap in the host-configured schema_format envelope
    if (this.schemaFormat === "markdown") {
      const columns = this.listColumns(detail);
      const text = _dataToCsv(rows, { columns, fenceBlock: "Available Tools" });
      return { success: true, data: text };
    }

    if (this.schemaFormat === "csv") {
      const columns = this.listColumns(detail);
      const text = _dataToCsvWithTypeHints(rows, { columns, comment: "Available Tools" });
      return { success: true, data: text };
    }

    // schemaFormat === "json" (or unrecognized, fall through to JSON)
    return { success: true, data: { tools: rows, count: rows.length } };
  }

  private buildListRows(detail: string): Record<string, unknown>[] {
    return Array.from(this.tools.values())
      .filter((t) => !t.isHidden)
      .map((t) => {
        const entry: Record<string, unknown> = { name: t.name, description: t.description };
        if (detail === "schema") {
          entry.schema = t.schema;
        } else if (detail === "params") {
          entry.params = schemaToCompactParams(t.schema as Record<string, unknown>);
        }
        // detail === "names": just name + description
        return entry;
      });
  }

  private listColumns(detail: string): string[] {
    if (detail === "schema") {
      return ["name", "description", "schema"];
    }
    if (detail === "params") {
      return ["name", "description", "params"];
    }
    return ["name", "description"];
  }

  private listMcpTools(serverId: string, _detail: string = "params"): ToolResult {
    if (!this.mcpRegistry) {
      return { success: false, error: 'No MCP registry configured' };
    }
    const server = this.mcpRegistry.getServer(serverId);
    if (!server) {
      return { success: false, error: `MCP server not found: ${serverId}` };
    }
    try {
      const tools = server.listTools().map((t) => ({ name: t.name, description: t.description ?? '' }));
      return { success: true, data: { tools, count: tools.length, mcp: serverId } };
    } catch (e) {
      return { success: false, error: `Failed to list MCP tools for ${serverId}: ${e}` };
    }
  }

  private handleExplain(params: Record<string, unknown>): ToolResult {
    const toolNames = (params.toolNames as string[]) ?? [];
    if (toolNames.length === 0) {
      return { success: false, error: 'explain requires at least one tool name in toolNames' };
    }

    // MCP routing
    if (params.mcp) {
      return this.explainMcpTools(toolNames, params.mcp as string);
    }

    // Per-call format override: 'json' forces raw schema regardless of default
    const perCallFormat = params.format as string | undefined;
    const effectiveFormat = perCallFormat === 'json' ? 'json' : this.schemaFormat;

    const explanations: Record<string, unknown> = {};
    const notFound: string[] = [];

    for (const name of toolNames) {
      const tool = this.tools.get(name);
      if (tool) {
        if (effectiveFormat === 'markdown') {
          explanations[name] = _schemaToMarkdown(tool.schema as Record<string, unknown>, {
            title: name,
            description: tool.description,
          });
        } else if (effectiveFormat === 'csv') {
          try {
            explanations[name] = _schemaToCsv(tool.schema as Record<string, unknown>, name);
          } catch {
            explanations[name] = '';
          }
        } else {
          explanations[name] = { description: tool.description, schema: tool.schema };
        }
      } else {
        notFound.push(name);
      }
    }

    if (Object.keys(explanations).length === 0) {
      return { success: false, error: `Tools not found: ${notFound.join(', ')}` };
    }

    if (effectiveFormat === 'markdown' || effectiveFormat === 'csv') {
      const sep = effectiveFormat === 'markdown' ? '\n\n' : '\n';
      const text = Object.values(explanations).join(sep);
      const notFoundText = notFound.length > 0 ? `\n\n# Not found: ${notFound.join(', ')}` : '';
      return { success: true, data: text + notFoundText };
    }

    // JSON envelope
    const result: Record<string, unknown> = { explanations };
    if (notFound.length > 0) result.not_found = notFound;
    return { success: true, data: result };
  }

  private explainMcpTools(toolNames: string[], serverId: string): ToolResult {
    if (!this.mcpRegistry) {
      return { success: false, error: 'No MCP registry configured' };
    }
    const server = this.mcpRegistry.getServer(serverId);
    if (!server) {
      return { success: false, error: `MCP server not found: ${serverId}` };
    }
    try {
      return { success: true, data: server.explainTools(toolNames) };
    } catch (e) {
      return { success: false, error: `Failed to explain MCP tools for ${serverId}: ${e}` };
    }
  }

  private async handleRun(params: Record<string, unknown>, start: number): Promise<ToolResult> {
    const toolName = params.toolName as string | undefined;
    const subject = params.subject as string | undefined;
    const args = (params.args as Record<string, unknown>) ?? {};

    if (!toolName) return { success: false, error: 'run requires toolName' };
    if (['list', 'explain', 'run', 'servers', 'hints'].includes(toolName)) {
      return { success: false, error: `'${toolName}' is a toolbox command, not a tool to run. Call toolbox with command='${toolName}' instead.` };
    }
    if (!subject) return { success: false, error: 'run requires subject — explain what you are doing' };

    // MCP routing
    if (params.mcp) {
      return this.runMcpTool(toolName, args, params.mcp as string, start);
    }

    // Native tool
    const tool = this.tools.get(toolName);
    if (!tool) return { success: false, error: `Native tool not found: ${toolName}`, data: { tool_name: toolName } };

    try {
      const result = await tool.execute(args);
      const durationMs = Date.now() - start;
      return { success: true, data: { result, tool_name: toolName, source: 'native', duration_ms: durationMs } };
    } catch (e) {
      return { success: false, error: `Tool execution failed: ${e}`, data: { tool_name: toolName } };
    }
  }

  private async runMcpTool(
    toolName: string,
    args: Record<string, unknown>,
    serverId: string,
    start: number,
  ): Promise<ToolResult> {
    if (!this.mcpRegistry) {
      return { success: false, error: 'No MCP registry configured' };
    }
    const server = this.mcpRegistry.getServer(serverId);
    if (!server) {
      return { success: false, error: `MCP server not found: ${serverId}` };
    }
    try {
      const output = server.executeTool(toolName, args);
      const result = output instanceof Promise ? await output : output;
      const durationMs = Date.now() - start;
      return { success: true, data: { result, tool_name: toolName, source: 'mcp', mcp: serverId, duration_ms: durationMs } };
    } catch (e) {
      return { success: false, error: `MCP tool execution failed: ${e}`, data: { tool_name: toolName } };
    }
  }

  private handleServers(): ToolResult {
    if (!this.mcpRegistry) {
      return { success: false, error: 'No MCP registry configured' };
    }
    const servers = this.mcpRegistry.listServers();
    return { success: true, data: { servers, count: servers.length } };
  }

  private handleHints(params: Record<string, unknown>): ToolResult {
    const args = (params.args as Record<string, unknown>) ?? {};
    const method = (args.method as string)?.toUpperCase();

    if (!method) {
      return {
        success: true,
        data: {
          description: 'Manage universal hints for tool usage, gotchas, and MCP shortcuts.',
          schema: {
            method: { type: 'enum', values: ['READ', 'CREATE', 'UPDATE', 'DELETE'], required: true },
            category: { type: 'enum', values: ['tool', 'mcp-server', 'mcp-tool', 'general'] },
            key: { type: 'string' },
            id: { type: 'string' },
            hint: { type: 'string' },
          },
        },
      };
    }

    switch (method) {
      case 'READ': {
        let hintResults: Hint[];
        const hintId = args.id as string | undefined;
        if (hintId) {
          const hint = this.hintStore.getById(hintId);
          hintResults = hint ? [hint] : [];
        } else if (args.category && args.key) {
          hintResults = this.hintStore.read({ category: args.category as string, key: args.key as string });
        } else if (args.category) {
          hintResults = this.hintStore.read({ category: args.category as string });
        } else {
          hintResults = this.hintStore.read();
        }
        return { success: true, data: { hints: hintResults, count: hintResults.length } };
      }
      case 'CREATE': {
        const hint = this.hintStore.create({ category: args.category as string, key: args.key as string, hint: args.hint as string });
        return { success: true, data: { hint } };
      }
      case 'UPDATE': {
        const updated = this.hintStore.update({ hintId: args.id as string, hint: args.hint as string });
        if (!updated) return { success: false, error: `Hint ${args.id} not found` };
        return { success: true, data: { hint: updated } };
      }
      case 'DELETE': {
        const deleted = this.hintStore.delete({ hintId: args.id as string });
        return { success: deleted, data: { message: deleted ? `Deleted hint ${args.id}` : `Hint ${args.id} not found` } };
      }
      default:
        return { success: false, error: `Unknown hints method: ${method}` };
    }
  }
}

// ── Memory Hint Store ─────────────────────────────────────────────────

export class MemoryHintStore implements HintStore {
  private hints: Map<string, Hint> = new Map();

  read(params: { category?: string; key?: string } = {}): Hint[] {
    let results = Array.from(this.hints.values());
    if (params.category) results = results.filter((h) => h.category === params.category);
    if (params.key) results = results.filter((h) => h.key === params.key);
    return results;
  }

  getById(hintId: string): Hint | undefined {
    return this.hints.get(hintId);
  }

  create(params: { category: string; key: string; hint: string }): Hint {
    // Idempotent: check existing
    const existing = Array.from(this.hints.values()).find(
      (h) => h.category === params.category && h.key === params.key,
    );
    if (existing) return existing;

    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const hint: Hint = { id, category: params.category as Hint['category'], key: params.key, hint: params.hint, created_at: now, updated_at: now };
    this.hints.set(id, hint);
    return hint;
  }

  update(params: { hintId: string; hint: string }): Hint | undefined {
    const existing = this.hints.get(params.hintId);
    if (!existing) return undefined;
    const updated: Hint = { ...existing, hint: params.hint, updated_at: new Date().toISOString() };
    this.hints.set(updated.id, updated);
    return updated;
  }

  delete(params: { hintId: string }): boolean {
    return this.hints.delete(params.hintId);
  }
}
