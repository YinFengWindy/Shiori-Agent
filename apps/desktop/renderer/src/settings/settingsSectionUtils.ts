/** Parses a numeric settings input without replacing a valid persisted fallback. */
export function parseSettingsNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** Preserves a configured custom memory engine alongside the default option. */
export function getMemoryEngineOptions(currentValue: string): Array<{ value: string; label: string }> {
  const normalized = currentValue.trim();
  const options = [
    { value: "", label: "default" },
  ];
  if (normalized && normalized !== "default") {
    options.push({ value: normalized, label: normalized });
  }
  return options;
}
