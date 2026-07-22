export type DesktopPetPoint = { x: number; y: number };

/** Converts the system cursor location into a window origin using the pointer's original local offset. */
export function desktopPetPositionFromCursor(cursor: DesktopPetPoint, pointerOffset: DesktopPetPoint): DesktopPetPoint {
  return { x: cursor.x - pointerOffset.x, y: cursor.y - pointerOffset.y };
}
