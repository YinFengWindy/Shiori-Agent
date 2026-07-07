/** Normalizes session media payloads into renderer-safe file paths. */
export function normalizeSessionMediaPaths(media: unknown): string[] {
  if (!Array.isArray(media)) {
    return [];
  }
  return media
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}
