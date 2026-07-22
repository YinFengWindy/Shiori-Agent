import type { SpriteState } from "./spriteContract";

/** Codex waits for a small horizontal displacement before showing drag direction. */
export const petDragDirectionThreshold = 4;

/** Codex uses jumping as the playful pointer-hover acknowledgement. */
export const petHoverState: SpriteState = "jumping";

/** Resolves a directional row only after a meaningful horizontal drag movement. */
export function petDragState(previousScreenX: number, screenX: number): SpriteState | null {
  if (Math.abs(screenX - previousScreenX) < petDragDirectionThreshold) return null;
  return screenX < previousScreenX ? "running-left" : "running-right";
}
