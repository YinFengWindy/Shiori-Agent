import type { RoleFormState, RoleRecord } from "../shared/types";

const defaultMood = "平静";

type RoleMoodRuntimeConfig = {
  mood_catalog?: unknown;
  default_mood?: unknown;
  mood_illustration_bindings?: unknown;
};

export type RoleMoodConfig = {
  moodCatalog: string[];
  defaultMood: string;
  moodIllustrationBindings: Record<string, string>;
};

/** Builds a stable default role mood config. */
export function createDefaultRoleMoodConfig(): RoleMoodConfig {
  return {
    moodCatalog: [defaultMood],
    defaultMood,
    moodIllustrationBindings: {},
  };
}

/** Reads role mood config from role runtime config, normalizing invalid shapes. */
export function readRoleMoodConfig(role: Pick<RoleRecord, "runtime_config"> | null): RoleMoodConfig {
  const runtimeConfig = (role?.runtime_config ?? {}) as RoleMoodRuntimeConfig;
  const rawCatalog = Array.isArray(runtimeConfig.mood_catalog) ? runtimeConfig.mood_catalog : [];
  const moodCatalog = dedupeMoods(rawCatalog);
  const rawDefaultMood = String(runtimeConfig.default_mood ?? "").trim();
  const resolvedDefaultMood = rawDefaultMood || moodCatalog[0] || defaultMood;
  const finalCatalog = dedupeMoods([resolvedDefaultMood, ...moodCatalog]);
  const rawBindings = runtimeConfig.mood_illustration_bindings;
  const moodIllustrationBindings = normalizeMoodBindings(rawBindings, finalCatalog);

  return {
    moodCatalog: finalCatalog,
    defaultMood: resolvedDefaultMood,
    moodIllustrationBindings,
  };
}

/** Writes role mood config back into runtime config while preserving unrelated keys. */
export function writeRoleMoodConfigToRuntimeConfig(
  runtimeConfig: Record<string, unknown>,
  roleForm: Pick<RoleFormState, "moodCatalog" | "defaultMood" | "moodIllustrationBindings">,
): Record<string, unknown> {
  const normalizedCatalog = dedupeMoods([roleForm.defaultMood, ...roleForm.moodCatalog]);
  const resolvedDefaultMood = String(roleForm.defaultMood || "").trim() || normalizedCatalog[0] || defaultMood;
  const nextCatalog = dedupeMoods([resolvedDefaultMood, ...normalizedCatalog]);
  const nextBindings = normalizeMoodBindings(roleForm.moodIllustrationBindings, nextCatalog);

  return {
    ...runtimeConfig,
    default_mood: resolvedDefaultMood,
    mood_catalog: nextCatalog,
    mood_illustration_bindings: nextBindings,
  };
}

/** Returns whether two role mood configs are equivalent. */
export function roleMoodConfigEqual(
  left: Pick<RoleFormState, "moodCatalog" | "defaultMood" | "moodIllustrationBindings">,
  right: RoleMoodConfig,
): boolean {
  if (String(left.defaultMood).trim() !== right.defaultMood) {
    return false;
  }
  const leftCatalog = dedupeMoods(left.moodCatalog);
  if (leftCatalog.length !== right.moodCatalog.length) {
    return false;
  }
  if (leftCatalog.some((mood, index) => mood !== right.moodCatalog[index])) {
    return false;
  }
  const leftBindings = normalizeMoodBindings(left.moodIllustrationBindings, leftCatalog);
  const rightKeys = Object.keys(right.moodIllustrationBindings).sort();
  const leftKeys = Object.keys(leftBindings).sort();
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return leftKeys.every((key, index) => key === rightKeys[index] && leftBindings[key] === right.moodIllustrationBindings[key]);
}

function dedupeMoods(values: unknown[]): string[] {
  const seen = new Set<string>();
  const next: string[] = [];
  values.forEach((value) => {
    const normalized = String(value ?? "").trim();
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    next.push(normalized);
  });
  return next;
}

function normalizeMoodBindings(rawBindings: unknown, moodCatalog: string[]): Record<string, string> {
  if (!rawBindings || typeof rawBindings !== "object" || Array.isArray(rawBindings)) {
    return {};
  }
  const allowedMoods = new Set(moodCatalog);
  const next: Record<string, string> = {};
  Object.entries(rawBindings).forEach(([key, value]) => {
    const mood = String(key ?? "").trim();
    const path = String(value ?? "").trim();
    if (!mood || !path || !allowedMoods.has(mood)) {
      return;
    }
    next[mood] = path;
  });
  return next;
}
