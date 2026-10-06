import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  hasPetDragMoved,
  petDoubleClickSelectsMainWindow,
  petDragRelease,
  petDragSamplesWith,
  petDragState,
  petHoverState,
  type PetPointerSample,
} from "./interactionContract";
import type { SpriteState } from "./spriteContract";
import type { SurfaceHandle } from "@yinfengwindy/shiori-sdk";

type DragState = {
  pointerId: number;
  previousScreenX: number;
  previousScreenY: number;
  hasMoved: boolean;
  samples: PetPointerSample[];
};

/**
 * Maps renderer pointer gestures to Codex pet animation rows and DesktopSurface commands.
 *
 * Note what is *absent* compared with the pre-#181 version: there is no
 * per-move "the pointer is now here" call. The host follows the native cursor
 * itself once `beginDrag` hands it the grab offset, because only the main
 * process can read a cursor that has left the window — and a renderer
 * reporting coordinates every frame is exactly the IPC round-trip the surface
 * primitives exist to avoid. Pointer moves here now only drive the sprite's
 * facing direction, the throw-velocity samples, and the voice-gesture cancel.
 */
export function useCodexPetInteraction(
  surface: SurfaceHandle | null,
) {
  const [interactionState, setInteractionState] = useState<SpriteState | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<DragState | null>(null);
  const lastGestureWasDragRef = useRef(true);

  function setNextInteractionState(nextState: SpriteState | null): void {
    setInteractionState((current) => current === nextState ? current : nextState);
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    if (event.button !== 0 || !surface) return;
    event.preventDefault();
    surface.postToBackground({ kind: "voice.gesture", gesture: "press" });
    setNextInteractionState(null);
    lastGestureWasDragRef.current = true;
    dragRef.current = {
      pointerId: event.pointerId,
      previousScreenX: event.screenX,
      previousScreenY: event.screenY,
      hasMoved: false,
      samples: [pointerSample(event)],
    };
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    const bounds = event.currentTarget.getBoundingClientRect();
    surface.beginDrag({ x: event.clientX - bounds.left, y: event.clientY - bounds.top });
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const sample = pointerSample(event);
    drag.samples = petDragSamplesWith(drag.samples, sample);
    if (!hasPetDragMoved(drag.previousScreenX, drag.previousScreenY, event.screenX, event.screenY)) return;
    drag.hasMoved = true;
    surface?.postToBackground({ kind: "voice.gesture", gesture: "move" });
    const nextState = petDragState(drag.previousScreenX, event.screenX);
    drag.previousScreenX = event.screenX;
    drag.previousScreenY = event.screenY;
    if (nextState) setNextInteractionState(nextState);
  }

  function onPointerUp(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const release = petDragRelease(drag.samples, pointerSample(event), drag.hasMoved);
    dragRef.current = null;
    setIsDragging(false);
    lastGestureWasDragRef.current = release.hasMoved;
    // The host already knows where the surface is; only the throw velocity is
    // news, and only when the release was fast enough to be worth a glide.
    surface?.endDrag(release.velocity ?? undefined);
    surface?.postToBackground({ kind: "voice.gesture", gesture: "release" });
    setNextInteractionState(petHoverState);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function onPointerCancel(): void {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    setIsDragging(false);
    lastGestureWasDragRef.current = true;
    surface?.endDrag();
    surface?.postToBackground({ kind: "voice.gesture", gesture: "cancel" });
    setNextInteractionState(null);
  }

  function onPointerEnter(): void {
    if (!dragRef.current) setNextInteractionState(petHoverState);
  }

  function onPointerLeave(): void {
    if (!dragRef.current) setNextInteractionState(null);
  }

  function onDoubleClick(): void {
    if (petDoubleClickSelectsMainWindow(lastGestureWasDragRef.current)) surface?.activateMainWindow();
  }

  return {
    interactionState,
    isDragging,
    pointerHandlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onPointerEnter, onPointerLeave, onDoubleClick },
  };
}

function pointerSample(event: ReactPointerEvent<HTMLDivElement>): PetPointerSample {
  return { screenX: event.screenX, screenY: event.screenY, timeMs: event.timeStamp };
}
