import type { SceneBeat, WorldDay, WorldDetails } from "./types";

/** Return the mutable Day chapter from the immutable renderer read model. */
export function selectCurrentWorldDay(world: WorldDetails | null): WorldDay | null {
  if (!world) return null;
  return world.days.find((day) => day.dayIndex === world.currentDayIndex) ?? null;
}

/** Resolve the next durable scene plan to its Day event. */
export function selectPendingWorldScene(world: WorldDetails | null): SceneBeat | null {
  const plan = world?.presentation?.plans[0];
  if (!world || !plan) return null;
  for (const day of world.days) {
    const event = day.events.find((candidate) => candidate.id === plan.eventId);
    if (event?.presentationMode === "scene") return event;
  }
  return null;
}

/** Resolve any committed scene for replay or live presentation. */
export function selectWorldScene(world: WorldDetails | null, sceneId: string): SceneBeat | null {
  if (!world || !sceneId) return null;
  for (const day of world.days) {
    const event = day.events.find((candidate) => candidate.id === sceneId);
    if (event?.presentationMode === "scene") return event;
  }
  return null;
}
