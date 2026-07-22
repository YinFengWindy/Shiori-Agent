import type { SpriteState } from "./spriteContract";

/** Codex waits for a small horizontal displacement before showing drag direction. */
export const petDragDirectionThreshold = 4;

/** Codex uses jumping as the playful pointer-hover acknowledgement. */
export const petHoverState: SpriteState = "jumping";

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

/** Resolves a directional row only after a meaningful horizontal drag movement. */
export function petDragState(previousScreenX: number, screenX: number): SpriteState | null {
  if (Math.abs(screenX - previousScreenX) < petDragDirectionThreshold) return null;
  return screenX < previousScreenX ? "running-left" : "running-right";
}
