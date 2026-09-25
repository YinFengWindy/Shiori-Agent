/** Parses a numeric settings input without replacing a valid persisted fallback. */
export function parseSettingsNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** Display names for memory engines the app ships; any other configured name shows as written. */
const memoryEngineLabels: Record<string, string> = { akasha: "Akasha" };

/** Preserves a configured custom memory engine alongside the default option. */
export function getMemoryEngineOptions(currentValue: string): Array<{ value: string; label: string }> {
  const normalized = currentValue.trim();
  const options = [
    { value: "", label: "默认" },
  ];
  if (normalized && normalized !== "default") {
    options.push({ value: normalized, label: memoryEngineLabels[normalized] ?? normalized });
  }
  return options;
}
