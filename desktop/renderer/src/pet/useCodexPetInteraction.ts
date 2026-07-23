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

type PetDragBridge = Pick<Window["miraDesktop"], "beginPetDrag" | "movePet" | "endPetDrag" | "openPetRole">;

type DragState = {
  pointerId: number;
  previousScreenX: number;
  previousScreenY: number;
  hasMoved: boolean;
  samples: PetPointerSample[];
};

/** Maps renderer pointer gestures to Codex pet animation rows and main-process drag commands. */
export function useCodexPetInteraction(dragBridge: PetDragBridge | null) {
  const [interactionState, setInteractionState] = useState<SpriteState | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<DragState | null>(null);
  const lastGestureWasDragRef = useRef(true);

  function setNextInteractionState(nextState: SpriteState | null): void {
    setInteractionState((current) => current === nextState ? current : nextState);
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    if (event.button !== 0 || !dragBridge) return;
    event.preventDefault();
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
    dragBridge.beginPetDrag(
      event.clientX - bounds.left,
      event.clientY - bounds.top,
      event.screenX,
      event.screenY,
    );
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const sample = pointerSample(event);
    drag.samples = petDragSamplesWith(drag.samples, sample);
    if (!hasPetDragMoved(drag.previousScreenX, drag.previousScreenY, event.screenX, event.screenY)) return;
    drag.hasMoved = true;
    const nextState = petDragState(drag.previousScreenX, event.screenX);
    drag.previousScreenX = event.screenX;
    drag.previousScreenY = event.screenY;
    if (nextState) setNextInteractionState(nextState);
    dragBridge?.movePet(event.screenX, event.screenY);
  }

  function onPointerUp(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const release = petDragRelease(drag.samples, pointerSample(event), drag.hasMoved);
    dragRef.current = null;
    setIsDragging(false);
    lastGestureWasDragRef.current = release.hasMoved;
    dragBridge?.endPetDrag(
      release.sample.screenX,
      release.sample.screenY,
      release.velocity?.x,
      release.velocity?.y,
    );
    setNextInteractionState(petHoverState);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function onPointerCancel(): void {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    setIsDragging(false);
    lastGestureWasDragRef.current = true;
    dragBridge?.endPetDrag();
    setNextInteractionState(null);
  }

  function onPointerEnter(): void {
    if (!dragRef.current) setNextInteractionState(petHoverState);
  }

  function onPointerLeave(): void {
    if (!dragRef.current) setNextInteractionState(null);
  }

  function onDoubleClick(): void {
    if (petDoubleClickSelectsMainWindow(lastGestureWasDragRef.current)) dragBridge?.openPetRole();
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
