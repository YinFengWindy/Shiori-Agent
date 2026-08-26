import type { ModelEffort } from "./chatModelSelection";

/** Returns whether a value is one of the effort values accepted by the bridge. */
export function isModelEffort(value: string): value is ModelEffort {
  return value === "none" || value === "low" || value === "high" || value === "max";
}

/** Normalizes persisted or registration effort values without changing fallback semantics. */
export function normalizeModelEffort(value: unknown, fallback: ModelEffort): ModelEffort {
  const normalized = String(value ?? "");
  return isModelEffort(normalized) ? normalized : fallback;
}
