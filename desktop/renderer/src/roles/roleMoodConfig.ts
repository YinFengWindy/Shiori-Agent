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
  const rawBindings = runtimeConfig.mood_illustration_bindings;
  const rawDefaultMood = String(runtimeConfig.default_mood ?? "").trim();
  const moodIllustrationBindings = normalizeMoodBindings(rawBindings);
  const moodCatalog = Object.keys(moodIllustrationBindings);
  const resolvedDefaultMood = (
    rawDefaultMood && moodIllustrationBindings[rawDefaultMood]
      ? rawDefaultMood
      : moodCatalog[0] || defaultMood
  );

  return {
    moodCatalog,
    defaultMood: resolvedDefaultMood,
    moodIllustrationBindings,
  };
}

/** Writes role mood config back into runtime config while preserving unrelated keys. */
export function writeRoleMoodConfigToRuntimeConfig(
  runtimeConfig: Record<string, unknown>,
  roleForm: Pick<RoleFormState, "moodCatalog" | "defaultMood" | "moodIllustrationBindings">,
): Record<string, unknown> {
  const nextBindings = normalizeMoodBindings(roleForm.moodIllustrationBindings);
  const nextCatalog = Object.keys(nextBindings);
  const requestedDefaultMood = String(roleForm.defaultMood || "").trim();
  const resolvedDefaultMood = (
    requestedDefaultMood && nextBindings[requestedDefaultMood]
      ? requestedDefaultMood
      : nextCatalog[0] || defaultMood
  );

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
  const leftBindings = normalizeMoodBindings(left.moodIllustrationBindings);
  const leftCatalog = Object.keys(leftBindings);
  const leftDefaultMood = (
    String(left.defaultMood).trim() && leftBindings[String(left.defaultMood).trim()]
      ? String(left.defaultMood).trim()
      : leftCatalog[0] || defaultMood
  );
  if (leftDefaultMood !== right.defaultMood) {
    return false;
  }
  if (leftCatalog.length !== right.moodCatalog.length) {
    return false;
  }
  if (leftCatalog.some((mood, index) => mood !== right.moodCatalog[index])) {
    return false;
  }
  const rightKeys = Object.keys(right.moodIllustrationBindings).sort();
  const leftKeys = Object.keys(leftBindings).sort();
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return leftKeys.every((key, index) => key === rightKeys[index] && leftBindings[key] === right.moodIllustrationBindings[key]);
}

function normalizeMoodBindings(rawBindings: unknown): Record<string, string> {
  if (!rawBindings || typeof rawBindings !== "object" || Array.isArray(rawBindings)) {
    return {};
  }
  const next: Record<string, string> = {};
  Object.entries(rawBindings).forEach(([key, value]) => {
    const mood = String(key ?? "").trim();
    const path = String(value ?? "").trim();
    if (!mood || !path) {
      return;
    }
    next[mood] = path;
  });
  return next;
}
