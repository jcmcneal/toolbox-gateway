# AGENTS.md — Project Context for AI Assistants

## Project Overview

**toolbox-gateway** is a single-tool gateway pattern for LLM agents. Instead of exposing N tool schemas in the system prompt, it exposes 1 gateway tool (`toolbox`) and lets the agent discover, inspect, and execute tools on demand.

- **Repo:** https://github.com/jcmcneal/toolbox-gateway
- **Local:** /Users/jason/projects/toolbox-gateway/
- **Languages:** Python (packages/python/) and TypeScript/JS (packages/js/)
- **License:** MIT

## Architecture

```
toolbox-gateway/
  packages/
    python/src/toolbox_gateway/   # Python package (pip: toolbox-gateway)
      core.py          # Toolbox, Tool, ToolResult, command handlers
      schema.py        # schema_to_csv, schema_to_markdown, data_to_csv
      hints.py         # Hint dataclass, HintStore protocol, MemoryHintStore
      mcp.py           # MCPRegistry, MCPServerInfo
      backends/
        sqlite_store.py   # SQLiteHintStore
        redis_store.py    # RedisHintStore
      adapters/
        openai.py       # OpenAI function calling adapter
        langchain.py    # LangChain adapter
    js/src/                        # JS package (npm: toolbox-gateway)
      index.ts         # Toolbox class (mirrors Python core)
      schema.ts        # Schema formatting
      sqlite-store.ts  # SQLite hint store (better-sqlite3)
      mcp.ts           # MCPRegistry
  fixtures/                       # Shared contract test fixtures (JSON)
    list.json, explain.json, run.json, hints.json,
    hidden-tools.json, error-responses.json
  packages/python/tests/           # 73 Python tests
  packages/js/test/                # JS tests
```

## Key Design Principles

1. **Lazy over eager** — schemas enter context only when needed
2. **Deliberate execution** — `subject` field forces intent articulation on `run`
3. **Framework-agnostic** — core logic has zero framework dependencies
4. **Backward-compatible** — all new features are additive opts-in
5. **Dual-language parity** — Python and JS must validate against the same fixtures

## Commands

```bash
# Python
cd packages/python
pip install -e ".[schema]"
pytest                    # 73 tests

# JS
cd packages/js
npm install
npm test
```

## Naming Conventions

- pip = npm = repo = `toolbox-gateway`
- Python import: `from toolbox_gateway import Toolbox, Tool`
- JS import: `import { Toolbox } from 'toolbox-gateway'`
- Class: `Toolbox`
- LLM tool name: `toolbox`
- Default SQLite path: `.toolbox_gateway/hints.db`

## Release Pitfall

Always: bump version → commit → push → tag → push tag. Do NOT push the tag before bumping version strings.

## Current Improvements

See `REQUIREMENTS.md` in the repo root for 5 planned improvements with acceptance criteria.
