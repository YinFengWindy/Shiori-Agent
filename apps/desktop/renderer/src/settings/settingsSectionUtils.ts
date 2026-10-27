/**
 * Parses numeric settings text only once it is a complete number; empty text
 * and intermediate forms such as `0.` or `1e` return null so callers keep
 * their persisted value instead of reporting a guess.
 */
export function parseCompleteSettingsNumber(value: string): number | null {
  const text = value.trim();
  if (!/^[+-]?(\d+(\.\d+)?|\.\d+)([eE][+-]?\d+)?$/.test(text)) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}
