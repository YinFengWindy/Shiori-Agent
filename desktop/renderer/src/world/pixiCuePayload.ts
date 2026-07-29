import type { PresentationCue } from "./presentationProtocol";

/** Returns the first non-empty string field in cue-compatible naming styles. */
export function stringCueValue(record: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

/** Returns the first finite numeric field in cue-compatible naming styles. */
export function numericCueValue(record: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

/** Resolves named or numeric character positions into one normalized stage slot. */
export function normalizedCharacterPosition(value: unknown, index: number, total: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value === "left") return 0.22;
  if (value === "right") return 0.78;
  if (value === "center") return 0.5;
  return total <= 1 ? 0.5 : (index + 1) / (total + 1);
}

/** Reads a sanitized object array from a plural cue payload field. */
export function cuePayloadItems(cue: PresentationCue, key: "items" | "tasks"): Record<string, unknown>[] {
  const value = cue.payload[key];
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null && !Array.isArray(item))
    : [];
}
