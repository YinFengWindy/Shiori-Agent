import type {
  SceneBeat,
  WorldCatchUp,
  WorldDetails,
  WorldPresentationSessionStatus,
} from "./types";

export const presentationProtocolVersion = 1 as const;

export type PresentationCueKind = "dialogue" | "sprites" | "background" | "camera" | "audio" | "cg" | "text";

/** Renderer-side validated presentation cue envelope. */
export type PresentationCue = {
  schemaVersion: typeof presentationProtocolVersion;
  cueId: string;
  planId: string;
  sequence: number;
  kind: PresentationCueKind;
  payload: Record<string, unknown>;
  parallelGroup: string | null;
  blocking: boolean;
  completionState: string;
  skipState: string;
  checkpoint: boolean;
};

/** Renderer-side validated presentation plan envelope. */
export type PerformancePlan = {
  schemaVersion: typeof presentationProtocolVersion;
  planId: string;
  worldId: string;
  eventId: string;
  sourceSequence: number;
  cues: PresentationCue[];
};

/** Renderer-side validated persisted presentation session. */
export type WorldPresentationSession = {
  worldId: string;
  lastPresentedEventSequence: number;
  activePlanId: string | null;
  activeCueIndex: number;
  status: WorldPresentationSessionStatus;
  updatedAt: string;
};

/** Queue snapshot used by reconnect, pause/resume, and checkpoint calls. */
export type WorldPresentationState = {
  session: WorldPresentationSession;
  plans: PerformancePlan[];
};

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} must be a non-empty string`);
  return value;
}

function integer(value: unknown, label: string): number {
  if (!Number.isInteger(value) || Number(value) < 0) throw new Error(`${label} must be a non-negative integer`);
  return Number(value);
}

/** Validate an untrusted bridge payload before presentation code consumes it. */
export function parsePerformancePlan(value: unknown): PerformancePlan {
  const plan = record(value, "performance plan");
  if (plan.schemaVersion !== presentationProtocolVersion) throw new Error("unsupported presentation schema");
  const planId = text(plan.planId, "planId");
  const cuesValue = plan.cues;
  if (!Array.isArray(cuesValue)) throw new Error("cues must be an array");
  const cues = cuesValue.map((item, index) => {
    const cue = record(item, "cue");
    if (cue.schemaVersion !== presentationProtocolVersion) throw new Error("unsupported cue schema");
    if (integer(cue.sequence, "cue sequence") !== index) throw new Error("cue sequences must be contiguous");
    if (cue.planId !== planId) throw new Error("cue planId does not match its plan");
    const kind = cue.kind;
    if (!["dialogue", "sprites", "background", "camera", "audio", "cg", "text"].includes(String(kind))) throw new Error("unsupported cue kind");
    if (typeof cue.payload !== "object" || cue.payload === null || Array.isArray(cue.payload)) throw new Error("cue payload must be an object");
    if (cue.parallelGroup !== null && typeof cue.parallelGroup !== "string") throw new Error("parallelGroup must be a string or null");
    if (typeof cue.blocking !== "boolean" || typeof cue.checkpoint !== "boolean") throw new Error("cue flags are invalid");
    return {
      schemaVersion: presentationProtocolVersion,
      cueId: text(cue.cueId, "cueId"),
      planId,
      sequence: index,
      kind: kind as PresentationCueKind,
      payload: cue.payload as Record<string, unknown>,
      parallelGroup: cue.parallelGroup as string | null,
      blocking: cue.blocking,
      completionState: text(cue.completionState, "completionState"),
      skipState: text(cue.skipState, "skipState"),
      checkpoint: cue.checkpoint,
    };
  });
  return {
    schemaVersion: presentationProtocolVersion,
    planId,
    worldId: text(plan.worldId, "worldId"),
    eventId: text(plan.eventId, "eventId"),
    sourceSequence: integer(plan.sourceSequence, "sourceSequence"),
    cues,
  };
}

/** Validate a persisted presentation cursor and its derived plan queue. */
export function parsePresentationState(value: unknown): WorldPresentationState {
  const state = record(value, "presentation state");
  const sessionValue = record(state.session, "presentation session");
  const status = sessionValue.status;
  if (!["playing", "paused", "awaiting_action", "awaiting_barrier"].includes(String(status))) {
    throw new Error("unsupported presentation session status");
  }
  const activePlanId = sessionValue.activePlanId;
  if (activePlanId !== null && typeof activePlanId !== "string") {
    throw new Error("activePlanId must be a string or null");
  }
  const session = {
    worldId: text(sessionValue.worldId, "session worldId"),
    lastPresentedEventSequence: integer(sessionValue.lastPresentedEventSequence, "lastPresentedEventSequence"),
    activePlanId: activePlanId as string | null,
    activeCueIndex: integer(sessionValue.activeCueIndex, "activeCueIndex"),
    status: status as WorldPresentationSessionStatus,
    updatedAt: text(sessionValue.updatedAt, "session updatedAt"),
  };
  if (!Array.isArray(state.plans)) throw new Error("presentation plans must be an array");
  return {
    session,
    plans: state.plans.map(parsePerformancePlan),
  };
}

/** Validate presentation plans embedded in a world detail response. */
export function parseWorldDetailsPerformance(world: WorldDetails): WorldDetails {
  const parseBeat = (beat: SceneBeat) => beat.performancePlan
    ? { ...beat, performancePlan: parsePerformancePlan(beat.performancePlan) }
    : beat;
  return {
    ...world,
    presentation: world.presentation ? parsePresentationState(world.presentation) : undefined,
    days: world.days.map((day) => ({ ...day, events: day.events.map(parseBeat) })),
    scene: {
      ...world.scene,
      beats: world.scene.beats.map(parseBeat),
    },
  };
}

/** Validate presentation plans in a catch-up response before merging beats. */
export function parseWorldCatchUpPerformance(update: WorldCatchUp): WorldCatchUp {
  return {
    ...update,
    presentation: update.presentation ? parsePresentationState(update.presentation) : undefined,
    beats: update.beats.map((beat: SceneBeat) => beat.performancePlan ? { ...beat, performancePlan: parsePerformancePlan(beat.performancePlan) } : beat),
    world: update.world ? parseWorldDetailsPerformance(update.world) : undefined,
  };
}
