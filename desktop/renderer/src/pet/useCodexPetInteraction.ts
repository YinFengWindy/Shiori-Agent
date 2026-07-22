import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { hasPetDragMoved, petDragState, petHoverState } from "./interactionContract";
import type { SpriteState } from "./spriteContract";

type PetDragBridge = Pick<Window["miraDesktop"], "beginPetDrag" | "movePet" | "endPetDrag" | "openPetRole">;

type DragState = {
  pointerId: number;
  previousScreenX: number;
  previousScreenY: number;
  hasMoved: boolean;
};

/** Maps renderer pointer gestures to Codex pet animation rows and main-process drag commands. */
export function useCodexPetInteraction(dragBridge: PetDragBridge | null) {
  const [interactionState, setInteractionState] = useState<SpriteState | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<DragState | null>(null);

  function setNextInteractionState(nextState: SpriteState | null): void {
    setInteractionState((current) => current === nextState ? current : nextState);
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    if (event.button !== 0 || !dragBridge) return;
    event.preventDefault();
    setNextInteractionState(null);
    dragRef.current = {
      pointerId: event.pointerId,
      previousScreenX: event.screenX,
      previousScreenY: event.screenY,
      hasMoved: false,
    };
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    dragBridge.beginPetDrag(event.clientX, event.clientY, event.screenX, event.screenY);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
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
    dragRef.current = null;
    setIsDragging(false);
    if (!drag.hasMoved) dragBridge?.openPetRole();
    dragBridge?.endPetDrag();
    setNextInteractionState(petHoverState);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function onPointerCancel(): void {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    setIsDragging(false);
    dragBridge?.endPetDrag();
    setNextInteractionState(null);
  }

  function onPointerEnter(): void {
    if (!dragRef.current) setNextInteractionState(petHoverState);
  }

  function onPointerLeave(): void {
    if (!dragRef.current) setNextInteractionState(null);
  }

  return {
    interactionState,
    isDragging,
    pointerHandlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onPointerEnter, onPointerLeave },
  };
}
