import type { SceneBeat, WorldDetails, WorldOc, WorldRunStatus, WorldSummary, WorldTimelineEntry } from "./types";

/** Selects the active world without constructing a new fallback object. */
export function selectWorld(worlds: WorldSummary[], worldId: string) {
  return worlds.find((world) => world.id === worldId) ?? worlds[0] ?? null;
}

/** Selects the currently controlled OC. */
export function selectActiveOc(world: WorldDetails | null): WorldOc | null {
  if (!world) return null;
  return world.ocs.find((oc) => oc.id === world.activeOcId) ?? world.ocs.find((oc) => oc.isActive) ?? null;
}

/** Returns whether a player action can advance the shared world. */
export function canSubmitWorldAction(world: WorldDetails | null) {
  return Boolean(world && world.scene.barriers.length === 0 && world.status === "action_required" && world.activeOcId);
}

/** Maps lifecycle state to player-facing copy. */
export function getWorldStatusLabel(status: WorldRunStatus) {
  const labels: Record<WorldRunStatus, string> = {
    idle: "等待推进",
    running: "正在推进",
    action_required: "轮到你了",
    barrier: "等待决定",
    stopped: "已停止",
    resumable: "可以继续",
  };
  return labels[status];
}

/** Merges committed beats idempotently and keeps their narrative order stable. */
export function mergeCommittedBeats(current: SceneBeat[], incoming: SceneBeat[]) {
  if (incoming.length === 0) return current;
  const merged = new Map(current.map((beat) => [beat.id, beat]));
  for (const beat of incoming) merged.set(beat.id, beat);
  const next = [...merged.values()].sort((left, right) => left.order - right.order);
  if (next.length === current.length && next.every((beat, index) => beat === current[index])) return current;
  return next;
}

/** Applies OC-knowledge filtering to locally cached omniscient timeline entries. */
export function selectTimelineEntries(entries: WorldTimelineEntry[], perspective: "known" | "omniscient") {
  return perspective === "omniscient" ? entries : entries.filter((entry) => entry.visibility === "known");
}
