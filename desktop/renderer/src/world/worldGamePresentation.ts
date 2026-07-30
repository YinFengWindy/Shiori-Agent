import type { PerformancePlan, WorldPresentationSession } from "./presentationProtocol";
import type { SceneBeat, WorldDetails } from "./types";

export type WorldGamePresentationSelection = {
  plan: PerformancePlan | null;
  preloadPlan?: PerformancePlan;
  beat: SceneBeat | null;
  session: WorldPresentationSession | null;
  startCueIndex: number;
  canPlay: boolean;
};

function selectBeat(world: WorldDetails, plan: PerformancePlan | null): SceneBeat | null {
  if (plan) return world.scene.beats.find((beat) => beat.id === plan.eventId) ?? null;
  return [...world.scene.beats].reverse()[0] ?? null;
}

/** Selects the durable active plan and cursor without treating stale queues as playable. */
export function selectWorldGamePresentation(world: WorldDetails): WorldGamePresentationSelection {
  const plans = world.presentation?.plans ?? [];
  const session = world.presentation?.session ?? null;
  const activeIndex = session?.activePlanId
    ? plans.findIndex((candidate) => candidate.planId === session.activePlanId)
    : 0;
  const planIndex = activeIndex >= 0 ? activeIndex : 0;
  const queuedPlan = plans[planIndex] ?? null;
  const canPlay = Boolean(queuedPlan && (!session || session.status === "playing" || session.status === "paused"));
  const plan = canPlay ? queuedPlan : null;
  const startCueIndex = plan && session?.activePlanId === plan.planId
    ? Math.min(plan.cues.length, Math.max(0, session.activeCueIndex))
    : 0;

  return {
    plan,
    preloadPlan: plan ? plans[planIndex + 1] : undefined,
    beat: selectBeat(world, plan),
    session,
    startCueIndex,
    canPlay,
  };
}
