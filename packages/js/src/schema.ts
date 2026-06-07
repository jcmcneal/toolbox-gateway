/**
 * Schema formatting — convert JSON Schemas to compact LLM-friendly formats.
 *
 * Opt-in: ``npm install toolbox-gateway`` includes these utilities.
 *
 * This module provides two key utilities:
 *
 * 1. ``schemaToCsv`` — Convert a JSON Schema to a compact CSV header with type hints
 * 2. ``schemaToMarkdown`` — Convert a JSON Schema to markdown field documentation
 *
 * Both are designed for the ``toolbox explain`` command to return compact,
 * LLM-friendly tool documentation instead of raw JSON Schema blobs.
 */

// ── Types ─────────────────────────────────────────────────────────────

type JsonSchema = Record<string, unknown>;

// ── Type hint extraction ─────────────────────────────────────────────

function formatRangeHint(
  minVal: number | null | undefined,
  maxVal: number | null | undefined,
  prefix: string,
): string {
  if (minVal != null && maxVal != null) {
    return minVal === maxVal
      ? `{${prefix}:${minVal}}`
      : `{${prefix}:${minVal}-${maxVal}}`;
  }
  if (minVal != null) return `{${prefix}:${minVal}+}`;
  if (maxVal != null) return `{${prefix}:≤${maxVal}}`;
  return "";
}

function getLengthHint(fieldSchema: JsonSchema): string {
  const ftype = fieldSchema.type ?? "string";
  if (ftype === "string") {
    return formatRangeHint(
      fieldSchema.minLength as number | undefined,
      fieldSchema.maxLength as number | undefined,
      "len",
    );
  }
  if (ftype === "integer" || ftype === "number") {
    return formatRangeHint(
      fieldSchema.minimum as number | undefined,
      fieldSchema.maximum as number | undefined,
      "range",
    );
  }
  if (ftype === "array") {
    return formatRangeHint(
      fieldSchema.minItems as number | undefined,
      fieldSchema.maxItems as number | undefined,
      "len",
    );
  }
  return "";
}

function parseMetadataHints(description: string | null | undefined): string {
  /** Extract metadata hints from description like 'format:OCC|pattern:^[A-Z]+$'. */
  if (!description) return "";
  const match = description.match(/\(([^)]+)\)/);
  if (!match) return "";
  const metadataStr = match[1];
  const hints: string[] = [];
  for (const part of metadataStr.split("|")) {
    const pieces = part.split(":", 2);
    if (pieces.length === 2) {
      hints.push(`{${pieces[0]}:${pieces[1]}}`);
    }
  }
  return hints.join("");
}

function getTypeHint(fieldSchema: JsonSchema, includeFormat = true): string {
  /** Extract a compact type hint string from a JSON Schema field definition. */
  const lengthHint = getLengthHint(fieldSchema);
  const metadataHints = parseMetadataHints(fieldSchema.description as string | undefined);

  const appendHints = (base: string): string => base + lengthHint + metadataHints;

  // Enum
  if (fieldSchema.enum) {
    return appendHints((fieldSchema.enum as unknown[]).map(String).join("|"));
  }

  // Array
  if (fieldSchema.type === "array") {
    const items = (fieldSchema.items as JsonSchema) ?? {};
    if (Object.keys(items).length > 0) {
      const elemType = getTypeHint(items, false);
      return appendHints(`array(${elemType})`);
    }
    return appendHints("array");
  }

  // Object with properties
  if (fieldSchema.type === "object" && fieldSchema.properties) {
    const required = new Set(fieldSchema.required as string[] ?? []);
    const props = fieldSchema.properties as Record<string, JsonSchema>;
    const fields: string[] = [];
    for (const [key, prop] of Object.entries(props)) {
      const propType = getTypeHint(prop, false);
      const suffix = required.has(key) ? "" : "?";
      fields.push(`${key}${suffix}:${propType}`);
    }
    return appendHints(`object(${fields.join(", ")})`);
  }

  // Object without properties (dict/record)
  if (fieldSchema.type === "object") {
    return appendHints("json");
  }

  // Primitives
  const typeMap: Record<string, string> = {
    string: "string",
    number: "number",
    integer: "integer",
    boolean: "boolean",
  };
  return appendHints(typeMap[fieldSchema.type as string] ?? "string");
}

// ── CSV Schema ──────────────────────────────────────────────────────

export function schemaToCsv(
  schema: JsonSchema,
  comment?: string,
): string {
  /** Convert a JSON Schema to a compact CSV header line with type hints. */
  const resolved = resolveRef(schema);

  let properties: Record<string, JsonSchema> = {};
  let required: string[] = [];

  if (resolved.type === "array" && resolved.items) {
    const items = resolved.items as JsonSchema;
    properties = (items.properties as Record<string, JsonSchema>) ?? {};
    required = (items.required as string[]) ?? [];
  } else if (resolved.type === "object") {
    properties = (resolved.properties as Record<string, JsonSchema>) ?? {};
    required = (resolved.required as string[]) ?? [];
  } else if (resolved.properties) {
    properties = resolved.properties as Record<string, JsonSchema>;
    required = (resolved.required as string[]) ?? [];
  }

  const propKeys = Object.keys(properties);
  if (propKeys.length === 0) {
    throw new Error(
      `Schema must have properties (object or array with items). Got: ${Object.keys(resolved)}`,
    );
  }

  const fields: string[] = [];
  const typeHints: string[] = [];
  const optionals: boolean[] = [];

  for (const fieldName of propKeys) {
    const fieldSchema = properties[fieldName];
    fields.push(fieldName);
    const isOptional = !required.includes(fieldName);
    optionals.push(isOptional);
    typeHints.push(getTypeHint(fieldSchema));
  }

  // Build schema comment
  const schemaParts = fields.map(
    (f, i) => `${f} (${typeHints[i]})${optionals[i] ? "?" : ""}`,
  );
  const commentLine = comment ? `# ${comment}: ` : "# Schema: ";
  const headerLine = fields.join(",");

  return `${commentLine}${schemaParts.join(", ")}\n${headerLine}`;
}

// ── Markdown Schema ─────────────────────────────────────────────────

export function schemaToMarkdown(
  schema: JsonSchema,
  opts?: { title?: string; description?: string },
): string {
  const title = opts?.title;
  const description = opts?.description;
  /** Convert a JSON Schema to markdown field documentation. */
  const resolved = resolveRef(schema);

  const properties = (resolved.properties as Record<string, JsonSchema>) ?? {};
  const required = new Set(resolved.required as string[] ?? []);

  const lines: string[] = [];

  // Header
  let header = "### Tool Schema";
  if (title) header = `### ${title}`;
  if (description) header += `[${description}]`;
  lines.push(header);

  // Check for method-based API
  const methodField = properties.method ?? {};
  if (methodField.enum) {
    lines.push(
      "(This tool uses a method-based API. Specify the 'method' parameter to choose the operation)",
    );
  }

  // Fields
  if (Object.keys(properties).length > 0) {
    lines.push("**Fields:**");
    for (const [fieldName, fieldSchema] of Object.entries(properties)) {
      const typeHint = getTypeHint(fieldSchema);
      const isRequired = required.has(fieldName);
      let desc = ((fieldSchema.description as string) ?? "").trim();

      // Clean up description — strip metadata hints already captured in type
      const cleanDesc = parseMetadataHints(fieldSchema.description as string | undefined);
      if (cleanDesc) {
        // Remove the (format:...|pattern:...) part from description
        desc = desc.replace(/\([^)]*(?:format|pattern)[^)]*\)/g, "").trim();
      }

      const suffix = isRequired ? "" : "?";
      let line = `- \`${fieldName}\` (${typeHint})${suffix}`;
      if (desc) line += `: ${desc}`;
      lines.push(line);
    }
  }

  return lines.join("\n");
}

// ── JSON to CSV data format ─────────────────────────────────────────

export function dataToCsv(
  data: Record<string, unknown>[],
  opts?: {
    columns?: string[];
    includeHeader?: boolean;
    fenceBlock?: string;
  },
): string {
  /** Convert a list of objects to CSV format for LLM consumption. */
  if (data.length === 0) return "";

  // Determine columns
  let columns = opts?.columns;
  if (!columns) {
    const seen: string[] = [];
    for (const row of data) {
      for (const key of Object.keys(row)) {
        if (!seen.includes(key)) seen.push(key);
      }
    }
    columns = seen;
  }

  const includeHeader = opts?.includeHeader ?? true;
  const lines: string[] = [];

  if (includeHeader) {
    lines.push(columns.join(","));
  }

  for (const row of data) {
    const values = columns.map((col) => escapeCsvField(row[col] ?? ""));
    lines.push(values.join(","));
  }

  const csvText = lines.join("\n");

  if (opts?.fenceBlock) {
    return `\`\`\`csv\n# ${opts.fenceBlock}\n${csvText}\n\`\`\``;
  }

  return csvText;
}

// ── Internal helpers ────────────────────────────────────────────────

function resolveRef(schema: JsonSchema): JsonSchema {
  /** Resolve $ref references in a JSON Schema. */
  if (schema["$ref"] && schema.definitions) {
    const refPath = (schema["$ref"] as string).replace("#/definitions/", "");
    const defs = schema.definitions as Record<string, JsonSchema>;
    return defs[refPath] ?? schema;
  }
  return schema;
}

function escapeCsvField(value: unknown): string {
  /** Escape a single value for CSV output. */
  if (value == null) return "";
  if (typeof value === "boolean") return String(value);
  if (Array.isArray(value) || (typeof value === "object" && value !== null)) {
    const s = JSON.stringify(value);
    if (s.includes(",") || s.includes('"') || s.includes("\n")) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  }
  const s = String(value);
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}
