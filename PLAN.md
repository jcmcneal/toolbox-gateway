# Implementation Plan — Toolbox-Gateway v0.5.x

OpenCode plan mode prompt. Execute in order. Each task is scoped to one logical change with a test-first approach.

---

## Task 1: Compact inline params on list

**Priority:** High | **Effort:** Small

### Python

1. `packages/python/src/toolbox_gateway/core.py` — `_handle_list`
   - Add `detail` parameter (default `names`) to `_handle_list` signature
   - When `detail=compact`, call the existing `data_to_csv` / type-hint pipeline on each tool's schema properties to produce a `params` string per tool entry
   - Update `ToolboxCommand.LIST` dispatch in `handle()` to forward the `detail` kwarg

2. `packages/python/src/toolbox_gateway/core.py` — `get_tool_definition`
   - Add optional `detail` property to the `command=list` parameter schema (enum: `names`, `compact`)

3. `packages/python/tests/test_core.py` — Add `TestListCompact`
   - `test_list_compact_includes_params`: assert `detail=compact` returns `params` per tool
   - `test_list_compact_empty_schema`: assert `params` is empty string for tools with no schema
   - `test_list_default_unchanged`: assert calling list without `detail` returns same shape as before

4. `fixtures/list.json` — Add `compact_variant` fixture with expected `params` field

### JS

5. `packages/js/src/index.ts` — `handleList`
   - Add `detail` param (default `names`) to `handleList`
   - When `detail=compact`, call `dataToCsv` on each tool's schema to produce `params`

6. `packages/js/src/index.ts` — `TOOLBOX_SCHEMA`
   - Add `detail` property to `command=list` params

7. `packages/js/test/core.test.ts` — Add `describe(list compact)` with matching tests

---

## Task 2: Opt-in schema validation on run

**Priority:** Medium | **Effort:** Medium

### Python

1. `packages/python/src/toolbox_gateway/core.py` — `Toolbox.__init__`
   - Add `validate_args: bool = False` parameter
   - Store as `self._validate_args`

2. `packages/python/src/toolbox_gateway/core.py` — `_handle_run`
   - Before `tool.execute`, if `self._validate_args` and tool.schema has properties, validate `args` against tool.schema using `jsonschema.validate`
   - On `ValidationError`, return `ToolResult(success=False, error=format_validation_error(...))`
   - Empty schemas (`{}`) skip validation
   - Add `_format_validation_error` helper producing: `Validation error: field is not a valid property. Expected: prop1 (type), prop2 (type)?`

3. `packages/python/pyproject.toml` — Add `jsonschema` as optional dep under `[project.optional-dependencies]` validate group

4. `packages/python/tests/test_core.py` — Add `TestRunValidation`
   - `test_validation_catches_unknown_property`
   - `test_validation_catches_missing_required`
   - `test_validation_catches_type_mismatch`
   - `test_validation_skipped_when_disabled`
   - `test_validation_skipped_for_empty_schema`

### JS

5. `packages/js/src/index.ts` — `Toolbox.constructor`
   - Add `validateArgs?: boolean` to opts, default `false`

6. `packages/js/src/index.ts` — `handleRun`
   - Before `tool.execute`, if `validateArgs` and schema has properties, validate using Zod
   - Dynamically build Zod schema from JSON Schema properties
   - On failure, return structured error message

7. `packages/js/test/core.test.ts` — Add matching validation tests

8. `fixtures/error-responses.json` — Add `validation_error` fixture

---

## Task 3: Unified native+MCP discovery

**Priority:** High | **Effort:** Small

### Python

1. `packages/python/src/toolbox_gateway/core.py` — `_handle_list`
   - When `mcp=all`, iterate `self._mcp_registry.list_servers()` and collect each server's tools via `server.list_tools()`
   - Merge with native tools in single `tools` array, each entry gets `source` field
   - Native tools: `source: native`, MCP tools: `source: server_id`
   - Keep `count` as total across all sources
   - Specific server ID (existing behavior): add `source` field to those entries too

2. `packages/python/tests/test_core.py` — Add `TestListMcpAll`
   - `test_list_mcp_all_returns_unified`: register 2 MCP servers, assert tools from both appear with `source`
   - `test_list_mcp_all_without_registry`: assert returns error same as `servers`
   - `test_list_native_includes_source`: assert native tools include `source: native`

### JS

3. `packages/js/src/index.ts` — `handleList`
   - Same `mcp=all` logic: merge native + all MCP server tools with `source` field

4. `packages/js/test/core.test.ts` — Add matching tests

5. `fixtures/list.json` — Add `mcp_all_variant` fixture

---

## Task 4: Hint staleness and self-pruning

**Priority:** Medium | **Effort:** Medium

### Python

1. `packages/python/src/toolbox_gateway/hints.py` — `Hint` dataclass
   - Add `last_used_at: str` (default = same as `created_at`)
   - Add `use_count: int` (default = 0)

2. `packages/python/src/toolbox_gateway/hints.py` — `HintStore` protocol
   - Add `prune(stale_days: int = 90, unused: bool = False) -> int`

3. `packages/python/src/toolbox_gateway/hints.py` — `MemoryHintStore`
   - Implement `prune`: filter by `last_used_at` age and `use_count == 0`
   - `read` must update `last_used_at` and increment `use_count` on each returned hint

4. `packages/python/src/toolbox_gateway/core.py` — `_handle_hints`
   - Handle `method=PRUNE` with `stale_days` and `unused` from args
   - Call `self._hint_store.prune(...)` and return count
   - Add `PRUNE` to the no-method schema documentation

5. `packages/python/src/toolbox_gateway/backends/sqlite_store.py` — `SQLiteHintStore`
   - `_ensure_db`: `ALTER TABLE hints ADD COLUMN last_used_at TEXT` and `ADD COLUMN use_count INTEGER DEFAULT 0` (guarded by pragma column check)
   - `read`: update `last_used_at` and `use_count` on each returned hint
   - Implement `prune` via DELETE WHERE

6. `packages/python/src/toolbox_gateway/backends/redis_store.py` — `RedisHintStore`
   - Include `last_used_at` and `use_count` in JSON payload
   - `read` updates these fields
   - Implement `prune` via SCAN + age check

7. `packages/python/tests/test_hints.py` — Add tests
   - `test_read_updates_use_metadata`
   - `test_prune_stale`
   - `test_prune_unused`
   - `test_hints_prune_command`
   - `test_no_method_docs_include_prune`

### JS

8. `packages/js/src/index.ts` — `Hint` interface, `MemoryHintStore`
   - Add `last_used_at: string`, `use_count: number`
   - Update `READ` to update metadata
   - Add `PRUNE` case to `handleHints`

9. `packages/js/src/sqlite-store.ts` — `SQLiteHintStore`
   - Same migration and read-update logic as Python

10. `packages/js/test/core.test.ts` — Add matching tests

11. `fixtures/hints.json` — Add `prune` fixture

---

## Task 5: Reactive provider refresh

**Priority:** Low | **Effort:** Small

### Python

1. `packages/python/src/toolbox_gateway/core.py` — `Toolbox.__init__`
   - Add `auto_refresh_interval: int | None = None` parameter
   - Add `self._last_refresh: float = time.monotonic()`

2. `packages/python/src/toolbox_gateway/core.py` — `_maybe_refresh` (new method)
   - Check if `auto_refresh_interval` is set and `time.monotonic() - self._last_refresh > self._auto_refresh_interval`
   - If so, call `self.refresh()` and update `self._last_refresh`

3. `packages/python/src/toolbox_gateway/core.py` — `_handle_list` and `_handle_explain`
   - Call `self._maybe_refresh()` at the top of each

4. `packages/python/tests/test_core.py` — Add `TestAutoRefresh`
   - `test_auto_refresh_triggers_after_interval`
   - `test_auto_refresh_does_not_trigger_within_interval`
   - `test_auto_refresh_disabled_by_default`
   - `test_run_does_not_trigger_refresh`

5. `packages/python/src/toolbox_gateway/core.py` — `from_provider` docstring
   - Document `auto_refresh_interval` parameter

### JS

6. `packages/js/src/index.ts` — `Toolbox.constructor`
   - Add `autoRefreshInterval?: number` to opts
   - Add `_lastRefresh: number` tracking
   - Add `_maybeRefresh()` private method
   - Call in `handleList` and `handleExplain`

7. `packages/js/test/core.test.ts` — Add matching tests

---

## Execution Order

| Step | Task | Depends on | Run tests after |
|------|-------|------------|-----------------|
| 1 | Task 1 (compact params) | Nothing | pytest and npm test |
| 2 | Task 3 (unified discovery) | Nothing | pytest and npm test |
| 3 | Task 2 (validation) | Nothing | pytest and npm test |
| 4 | Task 4 (hint staleness) | Nothing | pytest and npm test |
| 5 | Task 5 (auto-refresh) | Task 1 (list handler) | pytest and npm test |

Tasks 1-4 are independent. Task 5 goes last since it touches list/explain handlers.

After all tasks:
- Run full test suite
- Bump version in pyproject.toml and package.json
- Update README.md with new features