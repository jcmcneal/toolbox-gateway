# Toolbox-Gateway Improvement Requirements

Derived from agent-in-production review, June 2026.

---

## 1. Detail Levels on `list`

### Problem

Agents calling well-known tools (e.g. `web_search`) still pay a full turn for `explain` just to remember whether the parameter is `query` or `q`. The discover-inspect-run loop is correct for unknown tools, but unnecessarily expensive for familiar ones.

### Requirements

- `list` command MUST accept an optional `detail` parameter with five values:
  - `"params"` (default) — name, description, and a compact `params` hint string per tool
  - `"names"` — name and description only (the original behavior)
  - `"json"` — name, description, and full JSON Schema object per tool (inline `explain`)
  - `"markdown"` — name, description, and markdown-formatted schema per tool
  - `"csv"` — name, description, and CSV-formatted schema per tool
- When `detail=params` (default), each tool entry includes a `params` field with a compact CSV-type hint string derived from the tool's JSON Schema:
  - Example: `"query(string), limit(integer)?, offset(integer)?"`
  - The `?` suffix marks optional parameters.
  - Empty string `""` for tools with no schema or empty properties.
- When `detail=names`, output is just `name` and `description` — no extra fields.
- When `detail=json`, each tool entry includes a `schema` field with the tool's full JSON Schema object. Empty schema → `{}`.
- When `detail=markdown`, each tool entry includes a `schema_md` field with the tool's schema formatted as markdown (using existing `schema_to_markdown` / `schemaToMarkdown`). Empty schema → `""`.
- When `detail=csv`, each tool entry includes a `schema_csv` field with the tool's schema formatted as CSV (using existing `schema_to_csv` / `schemaToCsv`). Empty schema → `""`.
- This MUST NOT change the `get_tool_definition()` schema — `detail` is an optional parameter added to the existing `command=list` call.
- **Default change**: `list` with no `detail` parameter now returns `detail=params` (the most useful level). Callers who want the old minimal output can pass `detail=names`.
- The schema formatting utilities (`schema_to_csv`, `schema_to_markdown`, `schema_to_compact_params`) already exist in both `schema.py` and `schema.ts`. The `detail` dispatch in `_handle_list`/`handleList` should call the appropriate one.

### Example outputs

`detail=params` (default):
```json
{
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web for information.",
      "params": "query(string), limit(integer)?, offset(integer)?"
    }
  ],
  "count": 1
}
```

`detail=names`:
```json
{
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web for information."
    }
  ],
  "count": 1
}
```

`detail=json`:
```json
{
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web for information.",
      "schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    }
  ],
  "count": 1
}
```

`detail=markdown`:
```json
{
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web for information.",
      "schema_md": "### web_search\nGets data\n\n| Field | Type | Required | Description |\n|-------|------|----------|-------------|\n| query | string | yes | Search query |"
    }
  ],
  "count": 1
}
```

`detail=csv`:
```json
{
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web for information.",
      "schema_csv": "# Schema: web_search\nquery (string, required): Search query\nlimit (integer, optional): Max results"
    }
  ],
  "count": 1
}
```

### Acceptance Criteria

- [ ] `list` with no `detail` parameter returns `detail=params` (includes `params` per tool)
- [ ] `list` with `detail=names` returns only name + description
- [ ] `list` with `detail=json` includes full `schema` per tool
- [ ] `list` with `detail=markdown` includes `schema_md` per tool
- [ ] `list` with `detail=csv` includes `schema_csv` per tool
- [ ] `params` values generated via `schema_to_compact_params` / `schemaToCompactParams`
- [ ] `schema_md` values generated via `schema_to_markdown` / `schemaToMarkdown`
- [ ] `schema_csv` values generated via `schema_to_csv` / `schemaToCsv`
- [ ] Invalid `detail` values return `ToolResult(success=False, error=...)`
- [ ] Both Python and JS implementations match
- [ ] Fixture `fixtures/list.json` updated with all five variants

---

## 2. Schema Validation on `run` (Opt-In)

### Problem

Invalid arguments (typoed parameter names, wrong types) only surface when the tool itself fails, producing inconsistent error messages. The gateway sits between the agent and the tool but performs no validation.

### Requirements

- Toolbox constructor MUST accept an optional `validate_args: bool = False` parameter.
- When `validate_args=True`, the `_handle_run` method MUST validate `args` against the target tool's `schema` before calling `execute`.
- Validation MUST use `jsonschema.validate` (Python) / `zod` (JS) - both are already in the dependency orbit.
- On validation failure, `run` MUST return `ToolResult(success=False, error=...)` with a structured message identifying:
  - The field that failed
  - What was expected vs. what was received
  - Example: `"Validation error: 'queyr' is not a valid property. Expected: query (string), limit(integer)?"`
- When `validate_args=False` (default), behavior is unchanged - zero-cost for existing users.
- Tools with empty schemas (`schema={}`) MUST skip validation entirely (any args allowed).

### Acceptance Criteria

- [ ] `validate_args=False` (default) - no behavioral change
- [ ] `validate_args=True` catches unknown properties, type mismatches, missing required fields
- [ ] Error message includes field name and expected type
- [ ] Both Python and JS implementations match
- [ ] `fixtures/error-responses.json` updated with validation-error shape

---

## 3. Unified Tool Discovery Across Native and MCP

### Problem

When multiple MCP servers are connected alongside native tools, an agent must run `list`, then `servers`, then `list --mcp=X` per server. There is no single command showing all available tools in one view. Overlapping tool names across servers create additional ambiguity.

### Requirements

- `list` command MUST accept an optional `mcp` parameter value `"all"`.
- When `mcp=all`, the response MUST include tools from all sources - native tools plus tools from every registered MCP server - in a single `tools` array.
- Each tool entry MUST include a `source` field: `"native"` or the MCP server ID.
- If a tool name appears in multiple sources, ALL entries MUST be included (the agent chooses by `source`/`mcp` routing).
- Example output:
  ```json
  {
    "tools": [
      {"name": "web_search", "description": "...", "source": "native"},
      {"name": "navigate", "description": "...", "source": "chrome-devtools"},
      {"name": "get_state", "description": "...", "source": "homeassistant"}
    ],
    "count": 3
  }
  ```
- When `mcp` is omitted or is a specific server ID, behavior is unchanged.
- This MUST NOT require the `servers` command to be called first; the registry is already available.

### Acceptance Criteria

- [ ] `list` with `mcp=all` returns unified tool list
- [ ] Each tool includes `source` field
- [ ] Duplicate tool names across sources appear as separate entries
- [ ] `list` without `mcp` returns native-only (backward compat)
- [ ] `list` with `mcp=<serverId>` returns that server only (backward compat)
- [ ] Fixture `fixtures/list.json` updated with `mcp=all` variant

---

## 4. Hint Staleness and Self-Pruning

### Problem

Hints persist indefinitely. Once created, they are never removed unless manually deleted. Over time, hint stores accumulate obsolete advice from tools that changed their API, were removed, or had their parameter names renamed. There is no signal for an agent to know whether a hint is still relevant.

### Requirements

- The `Hint` dataclass/object MUST add two new fields:
  - `last_used_at: str` - ISO timestamp updated each time the hint is returned by a `READ` operation.
  - `use_count: int` - integer incremented each time the hint is returned by a `READ` operation.
- The `READ` operation MUST update `last_used_at` and increment `use_count` as a side effect of returning the hint. This is intentional side-effect-on-read behavior - hints that are actively consulted stay fresh.
- A new `prune` method MUST be added to `HintStore`:
  - `prune(*, stale_days: int = 90, unused: bool = False) -> int` - removes hints where `last_used_at` is older than `stale_days`, and/or hints where `use_count == 0` if `unused=True`. Returns count of pruned hints.
- The `hints` command MUST accept a new method: `PRUNE`.
  - Parameters: `stale_days` (default 90), `unused` (default false).
  - Returns count of removed hints.
- The auto-schema returned by calling `hints` with no method MUST document the `PRUNE` method.
- Existing hints without `last_used_at` / `use_count` MUST default to `last_used_at = created_at` and `use_count = 0` on first read after migration (backward compatible).
- SQLite schema MUST add `last_used_at` and `use_count` columns via `ALTER TABLE` migration in `_ensure_db`.
- Redis keys MUST include `last_used_at` and `use_count` in their JSON payload.

### Acceptance Criteria

- [ ] `Hint` includes `last_used_at` and `use_count`
- [ ] `READ` updates both fields
- [ ] `prune` removes stale/unused hints, returns count
- [ ] `hints` command with `method=PRUNE` works
- [ ] No-method `hints` call documents PRUNE
- [ ] SQLite migration adds columns without data loss
- [ ] Redis payloads include new fields
- [ ] Both Python and JS implementations match
- [ ] Fixture `fixtures/hints.json` updated

---

## 5. Reactive Provider Refresh

### Problem

`from_provider` fetches tools once at construction and again only on explicit `refresh()`. In long-running agent sessions, the host application may add or remove tools dynamically. The toolbox will serve stale tool lists until something manually calls `refresh()`, causing agents to discover tools to miss newly available ones.

### Requirements

- Toolbox MUST accept an optional `auto_refresh_interval: int | None = None` parameter (seconds).
- When set, `list` and `explain` commands MUST check whether `auto_refresh_interval` seconds have elapsed since the last refresh before executing. If so, they MUST call `refresh()` automatically before proceeding.
- A new `_last_refresh: float` internal timestamp MUST track the last refresh time.
- When `auto_refresh_interval=None` (default), no auto-refresh occurs - backward compatible.
- `from_provider` documentation MUST mention this option and recommend setting it for long-lived sessions.
- Auto-refresh MUST NOT apply to `run` - only `list` and `explain` (discovery commands). Running a stale tool will fail naturally with a clear "not found" error.

### Acceptance Criteria

- [ ] `auto_refresh_interval=None` - no behavioral change
- [ ] `auto_refresh_interval=60` - `list`/`explain` auto-refresh after 60s stale
- [ ] `run` does NOT trigger auto-refresh
- [ ] `_last_refresh` tracked internally
- [ ] Documentation updated for `from_provider` usage

---

## Appendix: Priority and Scope

| # | Requirement | Priority | Breaking Change |
|---|-------------|----------|-----------------|
| 1 | Detail levels on list (params/names/json/markdown/csv) | High | Minor: default changes from names→params |
| 2 | Opt-in schema validation on run | Medium | No |
| 3 | Unified native+MCP discovery | High | No |
| 4 | Hint staleness and self-pruning | Medium | No |
| 5 | Reactive provider refresh | Low | No |

All requirements are additive. Requirement 1 changes the default `list` output from names-only to params (the most useful shortcut), but `detail=names` preserves the old behavior for callers who want it.
