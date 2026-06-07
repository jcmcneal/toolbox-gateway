/**
 * SQLite hint store — lightweight persistent hints.
 *
 * Requires ``better-sqlite3`` as an optional peer dependency.
 * Falls back to MemoryHintStore if better-sqlite3 is not installed.
 *
 * Usage::
 *
 *     import { SQLiteHintStore } from 'toolbox-gateway';
 *     const store = new SQLiteHintStore();                          // .toolbox/hints.db
 *     const store = new SQLiteHintStore({ path: 'data/my_hints.db' });  // custom path
 */

import type { Hint, HintStore } from "./index.js";

// We use a dynamic import pattern so better-sqlite3 is truly optional.
// The ctor will throw at construction time if the module isn't available.

const DEFAULT_DB_PATH = ".toolbox/hints.db";

interface Sqlite3Database {
  exec(sql: string): void;
  prepare(sql: string): Sqlite3Statement;
  close(): void;
}

interface Sqlite3Statement {
  run(...params: unknown[]): { changes: number };
  get(...params: unknown[]): Record<string, unknown> | undefined;
  all(...params: unknown[]): Record<string, unknown>[];
}

export class SQLiteHintStore implements HintStore {
  private db: Sqlite3Database | null = null;
  private readonly path: string;

  constructor(opts?: { path?: string }) {
    this.path = opts?.path ?? DEFAULT_DB_PATH;
    // Lazy init — db opened on first operation so construction doesn't throw
    // if better-sqlite3 is missing and user never uses this store.
  }

  private ensureDb(): Sqlite3Database {
    if (this.db) return this.db;

    // Dynamic import — if better-sqlite3 is missing, throw a clear error
    let BetterSqlite3: new (path: string) => Sqlite3Database;
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      BetterSqlite3 = require("better-sqlite3") as new (
        path: string,
      ) => Sqlite3Database;
    } catch {
      throw new Error(
        "SQLiteHintStore requires better-sqlite3. Install it with: npm install better-sqlite3",
      );
    }

    // Create parent directory
    const { mkdirSync } = require("fs") as typeof import("fs");
    const { dirname } = require("path") as typeof import("path");
    mkdirSync(dirname(this.path), { recursive: true });

    this.db = new BetterSqlite3(this.path);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS hints (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        key TEXT NOT NULL,
        hint TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    this.db.exec(`
      CREATE UNIQUE INDEX IF NOT EXISTS idx_hints_category_key
      ON hints (category, key)
    `);

    return this.db;
  }

  private rowToHint(row: Record<string, unknown>): Hint {
    return {
      id: row.id as string,
      category: row.category as Hint["category"],
      key: row.key as string,
      hint: row.hint as string,
      created_at: row.created_at as string,
      updated_at: row.updated_at as string,
    };
  }

  read(params: { category?: string; key?: string } = {}): Hint[] {
    const db = this.ensureDb();
    let query = "SELECT * FROM hints";
    const conditions: string[] = [];
    const values: string[] = [];

    if (params.category) {
      conditions.push("category = ?");
      values.push(params.category);
    }
    if (params.key) {
      conditions.push("key = ?");
      values.push(params.key);
    }

    if (conditions.length > 0) {
      query += " WHERE " + conditions.join(" AND ");
    }

    const rows = db.prepare(query).all(...values);
    return rows.map((r) => this.rowToHint(r));
  }

  getById(hintId: string): Hint | undefined {
    const db = this.ensureDb();
    const row = db.prepare("SELECT * FROM hints WHERE id = ?").get(hintId);
    return row ? this.rowToHint(row) : undefined;
  }

  create(params: { category: string; key: string; hint: string }): Hint {
    const db = this.ensureDb();

    // Check for existing (idempotent)
    const existing = db
      .prepare("SELECT * FROM hints WHERE category = ? AND key = ?")
      .get(params.category, params.key) as Record<string, unknown> | undefined;

    if (existing) {
      return this.rowToHint(existing);
    }

    const id = crypto.randomUUID();
    const now = new Date().toISOString();

    db.prepare(
      "INSERT INTO hints (id, category, key, hint, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
    ).run(id, params.category, params.key, params.hint, now, now);

    return {
      id,
      category: params.category as Hint["category"],
      key: params.key,
      hint: params.hint,
      created_at: now,
      updated_at: now,
    };
  }

  update(params: { hintId: string; hint: string }): Hint | undefined {
    const db = this.ensureDb();
    const now = new Date().toISOString();

    const result = db
      .prepare("UPDATE hints SET hint = ?, updated_at = ? WHERE id = ?")
      .run(params.hint, now, params.hintId);

    if (result.changes === 0) return undefined;

    const row = db
      .prepare("SELECT * FROM hints WHERE id = ?")
      .get(params.hintId) as Record<string, unknown> | undefined;

    return row ? this.rowToHint(row) : undefined;
  }

  delete(params: { hintId: string }): boolean {
    const db = this.ensureDb();
    const result = db
      .prepare("DELETE FROM hints WHERE id = ?")
      .run(params.hintId);
    return result.changes > 0;
  }

  /** Close the database connection. Safe to call multiple times. */
  close(): void {
    if (this.db) {
      this.db.close();
      this.db = null;
    }
  }
}
