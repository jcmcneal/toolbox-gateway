import { describe, it, expect } from 'vitest';
import { Toolbox, MemoryHintStore, ToolInput, MCPRegistry, MCPServerInfo, schemaToCompactParams } from '../src/index.js';

// ── Helpers ────────────────────────────────────────────────────────

function makeTool(overrides: Partial<ToolInput> & { name: string }): ToolInput {
  return {
    description: `Tool: ${overrides.name}`,
    schema: {
      type: 'object',
      properties: {
        message: { type: 'string', description: 'A message' },
      },
      required: ['message'],
    },
    execute: (args) => ({ echo: args }),
    ...overrides,
  };
}

// ── list command (fixtures/list.json) ─────────────────────────────

describe('toolbox list', () => {
  it('returns all visible tools', async () => {
    const tb = new Toolbox([
      makeTool({ name: 'tool_a' }),
      makeTool({ name: 'tool_b' }),
      makeTool({ name: 'tool_c' }),
    ]);

    const result = await tb.handle('list', {});
    expect(result.success).toBe(true);
    expect(result.data).toBeDefined();
    const data = result.data as Record<string, unknown>;
    expect((data.tools as unknown[])).toHaveLength(3);
    expect(data.count).toBe(3);
  });

  it('hides tools with isHidden', async () => {
    const tb = new Toolbox([
      makeTool({ name: 'visible_tool' }),
      makeTool({ name: 'hidden_tool', isHidden: true }),
    ]);

    const result = await tb.handle('list', {});
    const data = result.data as Record<string, unknown>;
    const tools = data.tools as Array<{ name: string }>;
    expect(tools).toHaveLength(1);
    expect(tools[0].name).toBe('visible_tool');
    expect(tools.find((t: { name: string }) => t.name === 'hidden_tool')).toBeUndefined();
  });

  it('includes descriptions', async () => {
    const tb = new Toolbox([
      makeTool({ name: 'describe_me', description: 'Does something useful' }),
    ]);

    const result = await tb.handle('list', {});
    const data = result.data as Record<string, unknown>;
    const tools = data.tools as Array<{ name: string; description: string }>;
    expect(tools[0].description).toMatch(/useful/);
  });

  it('default detail is params', async () => {
    const tb = new Toolbox([makeTool({ name: 'test_tool' })]);
    const result = await tb.handle('list', {});
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.params).toBeDefined();
    expect(tool.params).not.toBe('');
  });

  it('detail=names returns name and description only', async () => {
    const tb = new Toolbox([makeTool({ name: 'test_tool' })]);
    const result = await tb.handle('list', { detail: 'names' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.params).toBeUndefined();
    expect(tool.schema).toBeUndefined();
    expect(tool.schema_md).toBeUndefined();
    expect(tool.schema_csv).toBeUndefined();
  });

  it('detail=json includes schema field', async () => {
    const tb = new Toolbox([makeTool({ name: 'test_tool' })]);
    const result = await tb.handle('list', { detail: 'json' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.schema).toBeDefined();
  });

  it('detail=markdown includes schema_md field', async () => {
    const tb = new Toolbox([makeTool({ name: 'test_tool' })]);
    const result = await tb.handle('list', { detail: 'markdown' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.schema_md).toBeDefined();
    expect(tool.schema_md).not.toBe('');
  });

  it('detail=csv includes schema_csv field', async () => {
    const tb = new Toolbox([makeTool({ name: 'test_tool' })]);
    const result = await tb.handle('list', { detail: 'csv' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.schema_csv).toBeDefined();
    expect(tool.schema_csv).not.toBe('');
  });

  it('detail=params explicit includes params field', async () => {
    const tb = new Toolbox([makeTool({ name: 'test_tool' })]);
    const result = await tb.handle('list', { detail: 'params' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.params).toBeDefined();
    expect(tool.params).not.toBe('');
  });

  it('invalid detail returns error', async () => {
    const tb = new Toolbox([makeTool({ name: 'test_tool' })]);
    const result = await tb.handle('list', { detail: 'invalid' });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/Invalid detail level/);
  });

  it('params for tool with empty schema is empty string', async () => {
    const tb = new Toolbox([
      { name: 'empty', description: 'No schema', schema: {}, execute: () => ({}) },
    ]);
    const result = await tb.handle('list', {});
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.params).toBe('');
  });

  it('json for tool with empty schema is {}', async () => {
    const tb = new Toolbox([
      { name: 'empty', description: 'No schema', schema: {}, execute: () => ({}) },
    ]);
    const result = await tb.handle('list', { detail: 'json' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.schema).toEqual({});
  });

  it('markdown for tool with empty schema is empty string', async () => {
    const tb = new Toolbox([
      { name: 'empty', description: 'No schema', schema: {}, execute: () => ({}) },
    ]);
    const result = await tb.handle('list', { detail: 'markdown' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.schema_md).toBe('');
  });

  it('csv for tool with empty schema is empty string', async () => {
    const tb = new Toolbox([
      { name: 'empty', description: 'No schema', schema: {}, execute: () => ({}) },
    ]);
    const result = await tb.handle('list', { detail: 'csv' });
    const data = result.data as Record<string, unknown>;
    const tool = (data.tools as Record<string, unknown>[])[0];
    expect(tool.schema_csv).toBe('');
  });
});

// ── explain command (fixtures/explain.json) ────────────────────────

describe('toolbox explain', () => {
  it('returns schema for named tools', async () => {
    const tb = new Toolbox([
      makeTool({ name: 'tool_a' }),
      makeTool({ name: 'tool_b' }),
    ]);

    const result = await tb.handle('explain', { toolNames: ['tool_a', 'tool_b'] });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    const exps = data.explanations as Record<string, Record<string, unknown>>;
    expect(exps.tool_a.description).toBeTruthy();
    expect(exps.tool_a.markdown).toBeTruthy();
    expect(exps.tool_b.markdown).toBeTruthy();
  });

  it('reports not_found for missing tools', async () => {
    const tb = new Toolbox([makeTool({ name: 'tool_a' })]);

    const result = await tb.handle('explain', { toolNames: ['tool_a', 'ghost'] });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    expect(data.not_found).toEqual(['ghost']);
    const exps = data.explanations as Record<string, unknown>;
    expect(exps.tool_a).toBeDefined();
  });

  it('fails when no toolNames provided', async () => {
    const tb = new Toolbox([makeTool({ name: 'tool_a' })]);

    const result = await tb.handle('explain', { toolNames: [] });
    expect(result.success).toBe(false);
    expect(result.error).toBeTruthy();
  });

  it('fails when all tools not found', async () => {
    const tb = new Toolbox([makeTool({ name: 'tool_a' })]);

    const result = await tb.handle('explain', { toolNames: ['ghost1', 'ghost2'] });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/ghost1|ghost2/);
  });

  it('returns markdown when schemaFormat=markdown (opt-in)', async () => {
    const tb = new Toolbox(
      [makeTool({ name: 'md_tool', description: 'Markdown test' })],
      { schemaFormat: 'markdown' },
    );

    const result = await tb.handle('explain', { toolNames: ['md_tool'] });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    const exps = data.explanations as Record<string, Record<string, unknown>>;
    expect(exps.md_tool.markdown).toBeTruthy();
    expect((exps.md_tool.markdown as string)).toMatch(/md_tool/);
    expect((exps.md_tool.markdown as string)).toMatch(/message/);
  });

  it('per-call format=json overrides markdown default', async () => {
    const tb = new Toolbox(
      [makeTool({ name: 'test_tool' })],
      { schemaFormat: 'markdown' },
    );

    const result = await tb.handle('explain', { toolNames: ['test_tool'], format: 'json' });
    const data = result.data as Record<string, unknown>;
    const exps = data.explanations as Record<string, Record<string, unknown>>;
    // Should be raw schema, not markdown
    expect(exps.test_tool.schema).toBeDefined();
    expect(exps.test_tool.markdown).toBeUndefined();
  });
});

// ── run command (fixtures/run.json) ───────────────────────────────

describe('toolbox run', () => {
  it('executes a tool and returns result', async () => {
    const tb = new Toolbox([
      makeTool({
        name: 'echo_tool',
        execute: (args) => ({ echoed: args }),
      }),
    ]);

    const result = await tb.handle('run', {
      toolName: 'echo_tool',
      subject: 'Testing echo functionality',
      args: { message: 'hello' },
    });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    expect(data.source).toBe('native');
    expect(data.result).toBeDefined();
    expect(data.duration_ms).toBeGreaterThanOrEqual(0);
  });

  it('requires toolName', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('run', { subject: 'No tool name provided' });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/toolName/i);
  });

  it('requires subject', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('run', { toolName: 'echo_tool' });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/subject/i);
  });

  it('unknown tool returns error', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('run', {
      toolName: 'ghost_tool',
      subject: 'Trying ghost tool',
    });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/not found/i);
  });

  it('hidden tools can still be executed', async () => {
    const tb = new Toolbox([
      makeTool({
        name: 'hidden_exec_tool',
        isHidden: true,
        execute: () => ({ secret: true }),
      }),
    ]);

    const result = await tb.handle('run', {
      toolName: 'hidden_exec_tool',
      subject: 'Testing hidden execution',
    });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    expect(data.source).toBe('native');
  });
});

// ── hints command (fixtures/hints.json) ────────────────────────────

describe('toolbox hints', () => {
  it('without method returns schema help', async () => {
    const tb = new Toolbox([], { hintStore: new MemoryHintStore() });

    const result = await tb.handle('hints', { args: {} });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    const schema = data.schema as Record<string, unknown>;
    expect(schema.method).toBeDefined();
    expect((schema.method as Record<string, unknown>).values).toContain('READ');
  });

  it('CREATE then READ shows new hint', async () => {
    const tb = new Toolbox([], { hintStore: new MemoryHintStore() });

    const create = await tb.handle('hints', {
      args: { method: 'CREATE', category: 'tool', key: 'my_tool', hint: 'Use uppercase' },
    });
    expect(create.success).toBe(true);

    const read = await tb.handle('hints', {
      args: { method: 'READ', category: 'tool' },
    });
    expect(read.success).toBe(true);
    const rdata = read.data as Record<string, unknown>;
    expect(rdata.count).toBeGreaterThanOrEqual(1);
    const hints = rdata.hints as Array<Record<string, unknown>>;
    expect(hints.some((h: Record<string, unknown>) => h.key === 'my_tool')).toBe(true);
  });

  it('CREATE is idempotent for same category+key', async () => {
    const tb = new Toolbox([], { hintStore: new MemoryHintStore() });

    const first = await tb.handle('hints', {
      args: { method: 'CREATE', category: 'tool', key: 'dedup', hint: 'First' },
    });
    const firstData = (first.data as Record<string, unknown>).hint as Record<string, unknown>;
    const firstId = firstData.id;

    const second = await tb.handle('hints', {
      args: { method: 'CREATE', category: 'tool', key: 'dedup', hint: 'Second' },
    });
    const secondData = (second.data as Record<string, unknown>).hint as Record<string, unknown>;
    // Same id, hint still "First"
    expect(secondData.id).toBe(firstId);
    expect(secondData.hint).toBe('First');
  });

  it('UPDATE changes hint text', async () => {
    const tb = new Toolbox([], { hintStore: new MemoryHintStore() });

    const create = await tb.handle('hints', {
      args: { method: 'CREATE', category: 'general', key: 'test', hint: 'Old' },
    });
    const created = ((create.data as Record<string, unknown>).hint as Record<string, unknown>);

    const update = await tb.handle('hints', {
      args: { method: 'UPDATE', id: created.id, hint: 'New' },
    });
    expect(update.success).toBe(true);
    const updated = (update.data as Record<string, unknown>).hint as Record<string, unknown>;
    expect(updated.hint).toBe('New');
    expect(updated.id).toBe(created.id);
  });

  it('DELETE removes hint', async () => {
    const tb = new Toolbox([], { hintStore: new MemoryHintStore() });

    const create = await tb.handle('hints', {
      args: { method: 'CREATE', category: 'general', key: 'temp', hint: 'Temporary' },
    });
    const created = ((create.data as Record<string, unknown>).hint as Record<string, unknown>);

    const del = await tb.handle('hints', {
      args: { method: 'DELETE', id: created.id },
    });
    expect(del.success).toBe(true);
    const delData = del.data as Record<string, unknown>;
    expect(delData.message).toMatch(/deleted/i);
  });

  it('READ by id returns single hint', async () => {
    const tb = new Toolbox([], { hintStore: new MemoryHintStore() });

    const create = await tb.handle('hints', {
      args: { method: 'CREATE', category: 'tool', key: 'single', hint: 'Only one' },
    });
    const created = ((create.data as Record<string, unknown>).hint as Record<string, unknown>);

    const read = await tb.handle('hints', {
      args: { method: 'READ', id: created.id },
    });
    expect(read.success).toBe(true);
    const rdata = read.data as Record<string, unknown>;
    expect(rdata.count).toBe(1);
  });

  it('READ by category+key returns matching hint', async () => {
    const tb = new Toolbox([], { hintStore: new MemoryHintStore() });

    await tb.handle('hints', {
      args: { method: 'CREATE', category: 'mcp-tool', key: 'get_data', hint: 'Needs auth' },
    });

    const read = await tb.handle('hints', {
      args: { method: 'READ', category: 'mcp-tool', key: 'get_data' },
    });
    expect(read.success).toBe(true);
    const rdata = read.data as Record<string, unknown>;
    expect(rdata.count).toBe(1);
  });
});

// ── error responses (fixtures/error-responses.json) ───────────────

describe('error responses', () => {
  it('unknown command', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('nonexistent' as string, {});
    expect(result.success).toBe(false);
    expect(result.error).toBeTruthy();
  });

  it('run without toolName', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('run', { subject: 'Missing tool name' });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/toolName/i);
  });

  it('run without subject', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('run', { toolName: 'some_tool' });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/subject/i);
  });

  it('explain with no tool names', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('explain', { toolNames: [] });
    expect(result.success).toBe(false);
    expect(result.error).toBeTruthy();
  });

  it('unknown tool for run', async () => {
    const tb = new Toolbox([makeTool({ name: 'echo_tool' })]);

    const result = await tb.handle('run', {
      toolName: 'ghost_123',
      subject: 'testing',
    });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/not found/i);
  });
});

// ── MCP registry ──────────────────────────────────────────────────

describe('MCP registry', () => {
  it('register and list servers', () => {
    const registry = new MCPRegistry();

    class TestServer implements MCPServerInfo {
      id = 'test';
      name = 'Test Server';
      use_when = 'Testing';
      priority = 10;
      listTools() { return [{ name: 'test_tool', description: 'A test tool' }]; }
      explainTools(names: string[]) { return { tools: names }; }
      executeTool(name: string, args: Record<string, unknown>) { return { name, args }; }
    }

    registry.registerServer(new TestServer());
    const servers = registry.listServers();
    expect(servers).toHaveLength(1);
    expect(servers[0].id).toBe('test');
    expect(servers[0].name).toBe('Test Server');
  });

  it('unregister removes server', () => {
    const registry = new MCPRegistry();

    class TestServer implements MCPServerInfo {
      id = 'temp';
      name = 'Temp';
      use_when = '';
      priority = 0;
      listTools() { return []; }
      explainTools(names: string[]) { return { tools: names }; }
      executeTool(name: string, args: Record<string, unknown>) { return { name, args }; }
    }

    registry.registerServer(new TestServer());
    registry.unregisterServer('temp');
    expect(registry.getServer('temp')).toBeUndefined();
  });

  it('toolbox list --mcp=serverId routes to MCP', async () => {
    const registry = new MCPRegistry();

    class StockServer implements MCPServerInfo {
      id = 'stocks';
      name = 'Stock API';
      use_when = 'Market data';
      priority = 5;
      listTools() { return [
        { name: 'get_stock_quote', description: 'Live quote' },
        { name: 'get_news', description: 'Latest news' },
      ]; }
      explainTools(_names: string[]) { return {}; }
      executeTool(_name: string, _args: Record<string, unknown>) { return {}; }
    }

    registry.registerServer(new StockServer());

    const tb = new Toolbox([], { mcpRegistry: registry });

    const result = await tb.handle('list', { mcp: 'stocks' });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    expect(data.count).toBe(2);
    expect(data.mcp).toBe('stocks');
  });

  it('toolbox list --mcp=unknown returns error', async () => {
    const registry = new MCPRegistry();
    const tb = new Toolbox([], { mcpRegistry: registry });

    const result = await tb.handle('list', { mcp: 'nonexistent' });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/not found/);
  });

  it('toolbox explain --mcp=serverId routes to MCP', async () => {
    const registry = new MCPRegistry();

    class MyServer implements MCPServerInfo {
      id = 'my';
      name = 'My';
      use_when = '';
      priority = 0;
      listTools() { return []; }
      explainTools(names: string[]) { return { schemas: names.map((n: string) => ({ name: n, type: 'object' })) }; }
      executeTool(_name: string, _args: Record<string, unknown>) { return {}; }
    }

    registry.registerServer(new MyServer());

    const tb = new Toolbox([], { mcpRegistry: registry });

    const result = await tb.handle('explain', { toolNames: ['tool_x'], mcp: 'my' });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    const schemas = data.schemas as Array<{ name: string }>;
    expect(schemas).toHaveLength(1);
    expect(schemas[0].name).toBe('tool_x');
  });

  it('toolbox run --mcp=serverId executes via MCP', async () => {
    const registry = new MCPRegistry();

    class ExecServer implements MCPServerInfo {
      id = 'exec';
      name = 'Exec';
      use_when = '';
      priority = 0;
      listTools() { return []; }
      explainTools(_names: string[]) { return {}; }
      executeTool(_name: string, args: Record<string, unknown>) { return { status: 'ok', ...args }; }
    }

    registry.registerServer(new ExecServer());

    const tb = new Toolbox([], { mcpRegistry: registry });

    const result = await tb.handle('run', {
      toolName: 'remote_tool',
      subject: 'Testing MCP execution',
      args: { key: 'value' },
      mcp: 'exec',
    });
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    expect(data.source).toBe('mcp');
    expect(data.mcp).toBe('exec');
    expect((data.result as Record<string, unknown>).status).toBe('ok');
  });

  it('toolbox servers lists registered servers', async () => {
    const registry = new MCPRegistry();

    class ServerA implements MCPServerInfo {
      id = 'a'; name = 'Alpha'; use_when = 'First'; priority = 10;
      listTools() { return []; }
      explainTools(_n: string[]) { return {}; }
      executeTool(_n: string, _a: Record<string, unknown>) { return {}; }
    }
    class ServerB implements MCPServerInfo {
      id = 'b'; name = 'Beta'; use_when = 'Second'; priority = 5;
      listTools() { return []; }
      explainTools(_n: string[]) { return {}; }
      executeTool(_n: string, _a: Record<string, unknown>) { return {}; }
    }

    registry.registerServer(new ServerA());
    registry.registerServer(new ServerB());

    const tb = new Toolbox([], { mcpRegistry: registry });

    const result = await tb.handle('servers', {});
    expect(result.success).toBe(true);
    const data = result.data as Record<string, unknown>;
    expect(data.count).toBe(2);
    const servers = data.servers as Array<{ id: string }>;
    // Sorted by priority descending
    expect(servers[0].id).toBe('a');
    expect(servers[1].id).toBe('b');
  });

  it('servers without MCP registry returns error', async () => {
    const tb = new Toolbox([]);

    const result = await tb.handle('servers', {});
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/No MCP registry/);
  });
});

// ── getToolDefinition ──────────────────────────────────────────────

describe('getToolDefinition', () => {
  it('returns a valid JSON Schema', () => {
    const tb = new Toolbox([]);
    const def = tb.getToolDefinition();

    expect(def.name).toBe('toolbox');
    expect(def.description).toBeTruthy();
    const params = def.parameters as Record<string, unknown>;
    expect(params.type).toBe('object');
    const props = params.properties as Record<string, unknown>;
    const cmd = props.command as Record<string, unknown>;
    expect(cmd.enum).toContain('list');
    expect(cmd.enum).toContain('explain');
    expect(cmd.enum).toContain('run');
    expect(cmd.enum).toContain('servers');
    expect(cmd.enum).toContain('hints');
  });
});

// ── Schema formatting tests ───────────────────────────────────────

describe('schema formatting', () => {
  it('schemaToCompactParams returns compact param string', () => {
    const result = schemaToCompactParams({
      type: 'object',
      properties: {
        query: { type: 'string' },
        limit: { type: 'integer' },
        offset: { type: 'integer' },
      },
      required: ['query'],
    });
    expect(result).toBe('query(string), limit(integer)?, offset(integer)?');
  });

  it('schemaToCompactParams handles empty schema', () => {
    expect(schemaToCompactParams({})).toBe('');
    expect(schemaToCompactParams({ type: 'object' })).toBe('');
  });

  it('schemaToCompactParams handles enums', () => {
    const result = schemaToCompactParams({
      type: 'object',
      properties: {
        role: { type: 'string', enum: ['admin', 'user'] },
      },
      required: ['role'],
    });
    expect(result).toBe('role(admin|user)');
  });

  it('schemaToCsv returns compact CSV header', async () => {
    const tb = new Toolbox([], { schemaFormat: 'markdown' });
    // schemaFormat only affects explain output; schemaToCsv is separate
    const { schemaToCsv } = await import('../src/schema.js');
    const csv = schemaToCsv({
      type: 'object',
      properties: {
        name: { type: 'string' },
        count: { type: 'integer', minimum: 0, maximum: 100 },
      },
      required: ['name'],
    }, 'Test');
    expect(csv).toContain('name');
    expect(csv).toContain('count');
    expect(csv).toContain('Test');
  });

  it('schemaToMarkdown returns field docs', async () => {
    const { schemaToMarkdown } = await import('../src/schema.js');
    const md = schemaToMarkdown({
      type: 'object',
      properties: {
        symbol: { type: 'string', description: 'Ticker symbol' },
        limit: { type: 'integer', description: 'Max results' },
      },
      required: ['symbol'],
    }, { title: 'MyTool', description: 'Gets data' });
    expect(md).toContain('MyTool');
    expect(md).toContain('Gets data');
    expect(md).toContain('symbol');
    expect(md).toContain('limit');
    expect(md).toContain('Ticker symbol');
  });
});
