import type { BridgeEvent } from "../../../src/shared";
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

/** Reduces one bridge event into a session-aware Codex task animation state. */
export function transitionPetActivity(
  activities: PetActivityBySession,
  event: BridgeEvent,
): PetActivityTransition {
  const sessionKey = eventSessionKey(event);
  if (!sessionKey) return { activities, state: resolvePetActivityState(activities), showNotification: false, handled: false };

  const nextActivities = { ...activities };
  let nextState: PetActivityState | null = null;
  let showNotification = false;
  if (event.method === "chat.delta") nextState = "running";
  if (event.method === "chat.done") nextState = "review";
  if (event.method === "chat.error") nextState = "failed";
  if (event.method === "session.updated") {
    const proactive = sessionNeedsUserReply(event);
    nextState = proactive ? "waiting" : "review";
    showNotification = proactive && activities[sessionKey] !== "waiting";
  }
  if (!nextState) return { activities, state: resolvePetActivityState(activities), showNotification: false, handled: false };
  nextActivities[sessionKey] = nextState;
  return { activities: nextActivities, state: resolvePetActivityState(nextActivities), showNotification, handled: true };
}

function eventSessionKey(event: BridgeEvent): string | null {
  const eventSessionKey = event.payload.session_key;
  if (typeof eventSessionKey === "string" && eventSessionKey) return eventSessionKey;
  if (event.method !== "session.updated") return null;
  const session = event.payload.session;
  if (!session || typeof session !== "object") return null;
  const key = (session as { key?: unknown }).key;
  return typeof key === "string" && key ? key : null;
}

function sessionNeedsUserReply(event: BridgeEvent): boolean {
  const session = event.payload.session;
  if (!session || typeof session !== "object") return false;
  const messages = (session as { messages?: unknown }).messages;
  if (!Array.isArray(messages) || messages.length === 0) return false;
  const lastMessage = messages[messages.length - 1];
  if (!lastMessage || typeof lastMessage !== "object") return false;
  const message = lastMessage as { role?: unknown; metadata?: unknown };
  if (message.role !== "assistant" || !message.metadata || typeof message.metadata !== "object") return false;
  return (message.metadata as { proactive?: unknown }).proactive === true;
}
