import type { DesktopPetPosition } from "./types.js";

export const desktopPetViewport = { width: 192, height: 208 };

/** Clamps the whole fixed pet viewport inside a display work area. */
export function clampDesktopPetPosition(
  position: DesktopPetPosition,
  workArea: { x: number; y: number; width: number; height: number },
): DesktopPetPosition {
  return {
    x: Math.min(Math.max(position.x, workArea.x), workArea.x + workArea.width - desktopPetViewport.width),
    y: Math.min(Math.max(position.y, workArea.y), workArea.y + workArea.height - desktopPetViewport.height),
  };
}
