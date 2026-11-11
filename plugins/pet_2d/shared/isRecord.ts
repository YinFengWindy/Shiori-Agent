/** Checks unknown JSON objects at plugin boundaries. */
export function isRecord(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === "object" && !Array.isArray(value)); }
