import {
  desktopPetBubbleGap,
  desktopPetViewport,
  resolveDesktopPetBubbleLayout,
} from "./geometry.js";
import type { DesktopPetPosition, DesktopPetWorkArea } from "./types.js";
import type { PetBubbleLayout } from "../observation/types.js";

export type DesktopPetWindowBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

/** Owns renderer-measured bubble layout and the transparent window bounds it requires. */
export class DesktopPetBubbleLayout {
  private height = 0;
  private current: PetBubbleLayout = { placement: "below", height: 0 };

  get layout(): PetBubbleLayout {
    return { ...this.current };
  }

  /** Updates the measured reply height and reports whether the window needs relayout. */
  setMeasuredHeight(height: number): boolean {
    if (!Number.isFinite(height)) return false;
    const nextHeight = Math.max(0, Math.ceil(height));
    if (nextHeight === this.height) return false;
    this.height = nextHeight;
    return true;
  }

  /** Resolves bubble placement and the window bounds for a clamped pet anchor point. */
  place(anchor: DesktopPetPosition, workArea: DesktopPetWorkArea): DesktopPetWindowBounds {
    this.current = resolveDesktopPetBubbleLayout(anchor, workArea, this.height);
    const bubbleOffset = this.current.height ? this.current.height + desktopPetBubbleGap : 0;
    return {
      x: anchor.x,
      y: this.current.placement === "above" ? anchor.y - bubbleOffset : anchor.y,
      width: desktopPetViewport.width,
      height: desktopPetViewport.height + bubbleOffset,
    };
  }

  /** Recovers the pet anchor from the window origin when no in-memory anchor is available. */
  anchorFromWindow(windowPosition: DesktopPetPosition): DesktopPetPosition {
    return {
      x: windowPosition.x,
      y: this.current.placement === "above"
        ? windowPosition.y + this.current.height + desktopPetBubbleGap
        : windowPosition.y,
    };
  }

  reset(): void {
    this.height = 0;
    this.current = { placement: "below", height: 0 };
  }
}
