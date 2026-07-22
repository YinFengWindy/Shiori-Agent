import type { SpriteState } from "./spriteContract";

/** Codex uses the jumping row for its playful pointer-hover acknowledgement. */
export const petHoverState: SpriteState = "jumping";
export const petDragDirectionThreshold = 4;

/** Resolves a directional movement row only after the pointer has moved horizontally. */
export function petDragState(previousScreenX: number, screenX: number): SpriteState | null {
  if (Math.abs(screenX - previousScreenX) < petDragDirectionThreshold) return null;
  return screenX < previousScreenX ? "running-left" : "running-right";
}
