/**
 * Pure JSON Schema -> form-field mapping used by the plugin config auto
 * form. Kept framework-free (no React, no DOM) so it is fully covered by
 * plain node:test unit tests; `PluginSchemaSettingsSection.tsx` only wires
 * these descriptors to input controls.
 *
 * Scope: a plugin's config model is a flat pydantic object in practice
 * (see `agent.plugin_host.config_schema`). Scalar properties (string,
 * number, integer, boolean, string enum) and lists of strings get a
 * dedicated control; anything this module cannot render safely (nested
 * objects, arrays of objects, unresolved `$ref`) falls back to a raw JSON
 * field, which still reads and writes correctly because the backend
 * re-validates the whole submission.
 *
 * Labels come from the pydantic `title`, hints from `description`, and a
 * number's unit from the `unit` key a model adds with
 * `Field(json_schema_extra={"unit": "秒"})`.
 */

/**
 * A JSON Schema fragment, permissive enough to cover pydantic's exports.
 * Only lists the fields this module actually reads.
 */
export type JsonSchema = {
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: unknown[];
  title?: string;
  description?: string;
  anyOf?: JsonSchema[];
  items?: JsonSchema;
  format?: string;
  writeOnly?: boolean;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  /** Display unit declared through pydantic `json_schema_extra`. */
  unit?: string;
};

export type PluginConfigFieldKind =
  | "string"
  | "secret"
  | "number"
  | "integer"
  | "boolean"
  | "enum"
  | "stringList"
  | "json";

export type PluginConfigField = {
  key: string;
  kind: PluginConfigFieldKind;
  label: string;
  hint?: string;
  required: boolean;
  /** Only present for kind "enum". */
  options?: string[];
  /** Display unit for number/integer fields. */
  unit?: string;
  /** Bounds for number/integer fields, when the schema declares them. */
  min?: number;
  max?: number;
};

const SECRET_NAME_HINTS = ["secret", "token", "password", "api_key", "apikey"];

/** Flags a string field as sensitive so it renders masked: pydantic `SecretStr` or a secret-shaped name. */
function looksLikeSecret(key: string, property: JsonSchema) {
  if (property.format === "password" || property.writeOnly) return true;
  const lowered = key.toLowerCase();
  return SECRET_NAME_HINTS.some((hint) => lowered.includes(hint));
}

/** Resolves the effective schema for a property, unwrapping a simple `anyOf` (Optional[X]). */
function resolveEffective(property: JsonSchema): JsonSchema {
  if (property.type || property.enum) return property;
  if (Array.isArray(property.anyOf)) {
    const candidate = property.anyOf.find((item) => item.type && item.type !== "null");
    if (candidate) return { ...candidate, ...property, type: candidate.type, enum: candidate.enum ?? property.enum };
  }
  return property;
}

function primaryType(schema: JsonSchema) {
  return Array.isArray(schema.type) ? schema.type[0] : schema.type;
}

function fieldKind(key: string, effective: JsonSchema): PluginConfigFieldKind {
  if (Array.isArray(effective.enum) && effective.enum.every((item) => typeof item === "string")) return "enum";
  switch (primaryType(effective)) {
    case "string":
      return looksLikeSecret(key, effective) ? "secret" : "string";
    case "integer":
      return "integer";
    case "number":
      return "number";
    case "boolean":
      return "boolean";
    case "array":
      // Only a list of plain strings has a native editor; object items stay raw JSON.
      return effective.items && primaryType(effective.items) === "string" && !effective.items.enum ? "stringList" : "json";
    default:
      // object, unresolved $ref, or an unrecognized/absent type.
      return "json";
  }
}

/** Converts a plugin's config JSON Schema into an ordered list of form fields. */
export function describePluginConfigFields(schema: JsonSchema): PluginConfigField[] {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  return Object.entries(properties).map(([key, property]) => {
    const effective = resolveEffective(property);
    const kind = fieldKind(key, effective);
    const field: PluginConfigField = {
      key,
      kind,
      label: property.title ?? key,
      hint: property.description,
      required: required.has(key),
    };
    if (kind === "enum" && Array.isArray(effective.enum)) {
      field.options = effective.enum.filter((item): item is string => typeof item === "string");
    }
    if (kind === "number" || kind === "integer") {
      if (effective.unit) field.unit = effective.unit;
      const min = effective.minimum ?? effective.exclusiveMinimum;
      const max = effective.maximum ?? effective.exclusiveMaximum;
      if (min !== undefined) field.min = min;
      if (max !== undefined) field.max = max;
    }
    return field;
  });
}

/**
 * Splits fields into the everyday form and the raw-JSON ones that go behind
 * an 「高级」 disclosure, keeping each group's schema order.
 */
export function partitionPluginConfigFields(fields: readonly PluginConfigField[]) {
  return {
    primary: fields.filter((field) => field.kind !== "json"),
    advanced: fields.filter((field) => field.kind === "json"),
  };
}

/** Reads a stored list value: anything that is not an array of strings becomes empty. */
export function readStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

/**
 * The variable name when a stored text value is a bare `${NAME}` reference.
 * The backend expands a reference whose variable exists when it loads
 * config.toml, so a reference that reaches the form verbatim is one whose
 * variable is not set in Shiori's environment.
 */
export function readEnvReference(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return /^\$\{(\w+)\}$/.exec(value.trim())?.[1] ?? null;
}
