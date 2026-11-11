/** Desktop-pet-internal JSON guards; deliberately not re-exported to providers. */

/** Checks unknown JSON objects at plugin boundaries. */
export function isRecord(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === "object" && !Array.isArray(value)); }
/** Checks nonempty identity fields without coercion. */
export function nonempty(value: unknown): value is string { return typeof value === "string" && value.trim().length > 0; }
