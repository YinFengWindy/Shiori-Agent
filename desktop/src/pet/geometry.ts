import type { DesktopPetPosition } from "./types.js";
import type { PetBubbleLayout } from "../observation/types.js";

export const desktopPetViewport = { width: 192, height: 208 };
export const desktopPetBubbleGap = 6;

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

/** Resolves the largest on-screen bubble area, preferring the space below the pet. */
export function resolveDesktopPetBubbleLayout(
  position: DesktopPetPosition,
  workArea: { x: number; y: number; width: number; height: number },
  requestedHeight: number,
): PetBubbleLayout {
  const height = Math.max(0, Math.ceil(requestedHeight));
  if (!height) return { placement: "below", height: 0 };

  const below = Math.max(
    0,
    workArea.y + workArea.height - position.y - desktopPetViewport.height - desktopPetBubbleGap,
  );
  const above = Math.max(0, position.y - workArea.y - desktopPetBubbleGap);
  if (height <= below || below >= above) {
    return { placement: "below", height: Math.min(height, below) };
  }
  return { placement: "above", height: Math.min(height, above) };
}
