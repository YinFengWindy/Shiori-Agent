import type { DesktopPetPosition } from "./types.js";

/** Codex advances released-pet momentum at this cadence. */
export const desktopPetMomentumIntervalMs = 8;
/** Codex limits a delayed momentum tick to this amount of elapsed time. */
export const desktopPetMomentumMaximumElapsedMs = 32;
/** Codex applies this velocity decay over every sixteen milliseconds. */
export const desktopPetMomentumDecayPerFrame = 0.88;
/** Codex stops the release glide once its speed becomes imperceptible. */
export const desktopPetMomentumMinimumSpeed = 65;
/** Codex never lets a released pet glide for longer than this. */
export const desktopPetMomentumMaximumDurationMs = 900;

export type DesktopPetMomentum = {
  position: DesktopPetPosition;
  velocity: DesktopPetPosition;
};

/** Advances one Codex-style release-momentum integration step. */
export function advanceDesktopPetMomentum(momentum: DesktopPetMomentum, elapsedMs: number): DesktopPetMomentum {
  const clampedElapsedMs = Math.min(Math.max(elapsedMs, 0), desktopPetMomentumMaximumElapsedMs);
  const elapsedSeconds = clampedElapsedMs / 1000;
  const decay = desktopPetMomentumDecayPerFrame ** (clampedElapsedMs / 16);
  return {
    position: {
      x: momentum.position.x + momentum.velocity.x * elapsedSeconds,
      y: momentum.position.y + momentum.velocity.y * elapsedSeconds,
    },
    velocity: {
      x: momentum.velocity.x * decay,
      y: momentum.velocity.y * decay,
    },
  };
}

/** Returns whether a Codex-style glide should settle and persist its last location. */
export function shouldStopDesktopPetMomentum(momentum: DesktopPetMomentum, elapsedSinceReleaseMs: number): boolean {
  return elapsedSinceReleaseMs >= desktopPetMomentumMaximumDurationMs
    || Math.hypot(momentum.velocity.x, momentum.velocity.y) < desktopPetMomentumMinimumSpeed;
}
