import type { PluginSettingValue, SettingsFormData } from "../../../src/shared.js";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

/** Reads one manifest-authorized value from the current settings draft. */
export function readPluginSetting(
  draft: SettingsFormData,
  configPath: string,
): PluginSettingValue | undefined {
  let current: unknown = draft;
  for (const segment of configPath.split(".")) {
    const record = asRecord(current);
    if (!record || !(segment in record)) return undefined;
    current = record[segment];
  }
  return typeof current === "string" || typeof current === "number" || typeof current === "boolean"
    ? current
    : undefined;
}

/** Applies an immutable update to one existing settings path declared by a plugin. */
export function writePluginSetting(
  draft: SettingsFormData,
  configPath: string,
  value: PluginSettingValue,
): SettingsFormData {
  const segments = configPath.split(".");

  function update(current: unknown, index: number): unknown {
    if (index === segments.length) return value;
    const record = asRecord(current);
    const segment = segments[index];
    if (!record || !segment || !(segment in record)) {
      throw new Error(`Unknown plugin settings path: ${configPath}`);
    }
    return { ...record, [segment]: update(record[segment], index + 1) };
  }

  return update(draft, 0) as SettingsFormData;
}
