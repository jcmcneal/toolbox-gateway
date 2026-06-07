# Tool Gateway (Toolbox)

Single-tool gateway pattern for LLM agents. Instead of bloating your system prompt with dozens of tool schemas, expose **one** tool — `toolbox` — and let the agent discover, inspect, and execute tools on demand.

Available as both a Python package (`pip install toolbox-gateway`) and a JavaScript package (`npm install toolbox-gateway`).

## The Pattern

```
Before:  15 tools × ~300 tokens/schema = ~4,500 tokens EVERY turn
After:   1 gateway tool × ~50 tokens = ~50 tokens EVERY turn
```

The toolbox collapses all tools into a single CLI-style interface:

- **list** — discover available tools
- **explain** — get full schema for specific tools on demand
- **run** — execute any tool by name
- **servers** — list connected MCP servers
- **hints** — CRUD for learned usage tips, gotchas, and shortcuts

## Packages

| Package | Registry | Directory | Status |
|---------|----------|-----------|--------|
| `toolbox-gateway` | [PyPI](https://pypi.org/project/toolbox-gateway/) | `packages/python/` | ✅ 73 tests |
| `toolbox-gateway` | [npm](https://npmjs.com/package/toolbox-gateway) | `packages/js/` | ✅ feature-complete |

Both packages share the same protocol semantics. See `fixtures/` for the shared contract test fixtures that validate both implementations against a single specification.

## Quick Start

### Python

```bash
pip install toolbox-gateway
```

```python
from toolbox_gateway import Toolbox, Tool

tools = [Tool(name="greet", description="Say hello",
    schema={"type":"object","properties":{"name":{"type":"string"}},"required":["name"]},
    execute=lambda args: f"Hello, {args['name']}!")]

tb = Toolbox(tools=tools)

# Single tool definition for your LLM
tb.get_tool_definition()

# Route commands
tb.handle(command="list")
tb.handle(command="run", toolName="greet", subject="Saying hello", args={"name":"World"})
```

### JavaScript

```bash
npm install toolbox-gateway
```

```js
import { Toolbox, MemoryHintStore, SQLiteHintStore, schemaToCsv } from 'toolbox-gateway';

// In-memory hint store (no deps)
const tb = new Toolbox([/* tools */], new MemoryHintStore());

// SQLite hint store (requires: npm install better-sqlite3)
const store = new SQLiteHintStore({ path: '.toolbox_gateway/hints.db' });

// Schema formatting
schemaToCsv(mySchema);
```

`better-sqlite3` is an optional dependency for `SQLiteHintStore`. The core (`Toolbox`, `MemoryHintStore`, schema utilities) has zero mandatory dependencies beyond `zod` (peer dep).

## Contract

Both packages validate against the shared test fixtures in `fixtures/`:

- `fixtures/list.json` — expected response shape for list
- `fixtures/explain.json` — expected response shape for explain
- `fixtures/run.json` — expected response shape for run
- `fixtures/hints.json` — expected response shape for hints
- `fixtures/hidden-tools.json` — hidden tool semantics
- `fixtures/error-responses.json` — error shape contract

## Design Principles

1. **Lazy over eager** — schemas enter context only when needed
2. **Deliberate execution** — `subject` field forces intent articulation
3. **Discoverable** — `list` and `explain` let agents reason about capabilities
4. **Memorable** — hints let agents learn and share usage patterns
5. **Framework-agnostic** — core logic has zero framework dependencies

## License

MIT
