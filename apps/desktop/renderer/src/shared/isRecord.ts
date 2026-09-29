/** Whether `value` is a plain object (not null, not an array), e.g. a bridge payload field. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
