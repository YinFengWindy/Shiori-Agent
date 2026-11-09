import type { SurfaceRoleActivity } from "@yinfengwindy/shiori-sdk";
import type { SpriteState } from "./spriteContract";

type PetActivityState = Extract<SpriteState, "failed" | "waiting" | "running" | "review">;
type PetActivityBySession = Record<string, PetActivityState>;

export type PetActivityTransition = {
  activities: PetActivityBySession;
  state: PetActivityState | "idle";
  showNotification: boolean;
  handled: boolean;
};

/** Keeps Codex's published task-state priority when more than one session is active. */
export const petActivityPriority: Record<PetActivityState, number> = {
  waiting: 4,
  failed: 3,
  review: 2,
  running: 1,
};

/** Returns the dominant Codex activity state, or idle when no task owns the pet. */
export function resolvePetActivityState(activities: PetActivityBySession): PetActivityState | "idle" {
  let current: PetActivityState | "idle" = "idle";
  for (const state of Object.values(activities)) {
    if (current === "idle" || petActivityPriority[state] > petActivityPriority[current]) current = state;
  }
  return current;
}

/** Reduces one role activity into a session-aware Codex task animation state. */
export function transitionPetActivity(
  activities: PetActivityBySession,
  event: SurfaceRoleActivity,
): PetActivityTransition {
  const sessionKey = event.sessionKey;
  if (!sessionKey) return { activities, state: resolvePetActivityState(activities), showNotification: false, handled: false };

  const nextActivities = { ...activities };
  const nextState = event.phase;
  const showNotification = event.notify && activities[sessionKey] !== "waiting";
  nextActivities[sessionKey] = nextState;
  return { activities: nextActivities, state: resolvePetActivityState(nextActivities), showNotification, handled: true };
}
