import type { SpriteState } from "./spriteContract";

/** Codex uses the waving row as its pointer-hover acknowledgement. */
export const petHoverState: SpriteState = "waving";

/** Resolves a directional movement row only after the pointer has moved horizontally. */
export function petDragState(previousScreenX: number, screenX: number): SpriteState | null {
  if (screenX === previousScreenX) return null;
  return screenX < previousScreenX ? "running-left" : "running-right";
}
