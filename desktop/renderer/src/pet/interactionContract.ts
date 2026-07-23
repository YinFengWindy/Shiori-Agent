import type { SpriteState } from "./spriteContract";

/** Codex waits for a small horizontal displacement before showing drag direction. */
export const petDragDirectionThreshold = 4;
/** Codex estimates throw velocity from at most this much recent pointer history. */
export const petDragVelocityWindowMs = 160;
/** Codex ignores low-speed releases instead of starting a barely visible glide. */
export const petDragVelocityThreshold = 320;
/** Codex caps released pet velocity so a single noisy sample cannot throw it away. */
export const petDragVelocityMaximum = 1600;
/** Codex guards zero-duration pointer samples when converting movement to velocity. */
export const petDragVelocityMinimumDurationMs = 8;

export type PetPointerSample = {
  screenX: number;
  screenY: number;
  timeMs: number;
};

export type PetDragRelease = {
  hasMoved: boolean;
  sample: PetPointerSample;
  velocity: { x: number; y: number } | null;
};

/** Codex uses jumping as the playful pointer-hover acknowledgement. */
export const petHoverState: SpriteState = "jumping";

/** A completed double click selects the main window only when the gesture never became a drag. */
export function petDoubleClickSelectsMainWindow(hasMoved: boolean): boolean {
  return !hasMoved;
}

/** Returns whether a pointer has left its click slop in either drag axis. */
export function hasPetDragMoved(
  previousScreenX: number,
  previousScreenY: number,
  screenX: number,
  screenY: number,
): boolean {
  return Math.abs(screenX - previousScreenX) >= petDragDirectionThreshold
    || Math.abs(screenY - previousScreenY) >= petDragDirectionThreshold;
}

/** Keeps only the most recent pointer history Codex uses for release velocity. */
export function petDragSamplesWith(sampleHistory: PetPointerSample[], sample: PetPointerSample): PetPointerSample[] {
  const samples = [...sampleHistory, sample];
  return samples.filter((candidate) => sample.timeMs - candidate.timeMs <= petDragVelocityWindowMs);
}

/** Resolves Codex's bounded throw velocity from recent meaningful pointer movement. */
export function petDragRelease(
  sampleHistory: PetPointerSample[],
  sample: PetPointerSample,
  hasMoved: boolean,
): PetDragRelease {
  const samples = petDragSamplesWith(sampleHistory, sample);
  const firstSample = samples[0] ?? sample;
  const moved = hasMoved || hasPetDragMoved(firstSample.screenX, firstSample.screenY, sample.screenX, sample.screenY);
  if (!moved) return { hasMoved: false, sample, velocity: null };

  const latest = latestMeaningfulPetDragSample(samples);
  const oldest = samples.find((candidate) => latest.timeMs - candidate.timeMs > 0);
  if (!oldest) return { hasMoved: true, sample, velocity: null };

  const durationSeconds = Math.max(latest.timeMs - oldest.timeMs, petDragVelocityMinimumDurationMs) / 1000;
  const velocity = {
    x: (latest.screenX - oldest.screenX) / durationSeconds,
    y: (latest.screenY - oldest.screenY) / durationSeconds,
  };
  const magnitude = Math.hypot(velocity.x, velocity.y);
  if (magnitude < petDragVelocityThreshold) return { hasMoved: true, sample, velocity: null };
  if (magnitude <= petDragVelocityMaximum) return { hasMoved: true, sample, velocity };
  const scale = petDragVelocityMaximum / magnitude;
  return { hasMoved: true, sample, velocity: { x: velocity.x * scale, y: velocity.y * scale } };
}

function latestMeaningfulPetDragSample(samples: PetPointerSample[]): PetPointerSample {
  const latest = samples.at(-1);
  if (!latest) throw new Error("cannot resolve a pet drag release without pointer samples");
  for (let index = samples.length - 1; index > 0; index -= 1) {
    const previous = samples[index - 1];
    if (hasPetDragMoved(latest.screenX, latest.screenY, previous.screenX, previous.screenY)) return samples[index];
  }
  return latest;
}

/** Resolves a directional row only after a meaningful horizontal drag movement. */
export function petDragState(previousScreenX: number, screenX: number): SpriteState | null {
  if (Math.abs(screenX - previousScreenX) < petDragDirectionThreshold) return null;
  return screenX < previousScreenX ? "running-left" : "running-right";
}
