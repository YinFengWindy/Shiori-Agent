import type { RoleRecord } from "../shared/types";
import type { StoryDetails } from "./types";

type StoryRoleSnapshot = StoryDetails["roleSnapshot"];
type StoryCharacterRole = Pick<RoleRecord, "avatar_abs" | "illustrations" | "illustrations_abs">;

/** Resolves the frozen Story mood illustration before falling back to role assets. */
export function resolveStoryCharacterIllustration(
  role: StoryCharacterRole | null,
  snapshot: StoryRoleSnapshot,
): string {
  if (!role) return "";

  const snapshotIllustrations = Array.isArray(snapshot.illustrations) ? snapshot.illustrations : [];
  const runtimeConfig = snapshot.runtime_config ?? {};
  const defaultMood = String(runtimeConfig.default_mood ?? "").trim();
  const bindings = runtimeConfig.mood_illustration_bindings;
  const boundIllustration = defaultMood && bindings && typeof bindings === "object" && !Array.isArray(bindings)
    ? String((bindings as Record<string, unknown>)[defaultMood] ?? "").trim()
    : "";
  if (boundIllustration) {
    const liveBoundIndex = role.illustrations.indexOf(boundIllustration);
    const boundIndex = liveBoundIndex >= 0 ? liveBoundIndex : snapshotIllustrations.indexOf(boundIllustration);
    const boundPath = boundIndex >= 0 ? role.illustrations_abs[boundIndex] : "";
    if (boundPath) return boundPath;
  }

  return role.illustrations_abs.find(Boolean) || role.avatar_abs || "";
}
