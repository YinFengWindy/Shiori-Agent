import type { DesktopPetPosition } from "./types.js";

/** Converts the system cursor location into a window origin using the pointer's original local offset. */
export function desktopPetPositionFromCursor(
  cursor: DesktopPetPosition,
  pointerOffset: DesktopPetPosition,
): DesktopPetPosition {
  return { x: cursor.x - pointerOffset.x, y: cursor.y - pointerOffset.y };
}
