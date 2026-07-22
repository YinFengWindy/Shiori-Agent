import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { petDragState, petHoverState } from "./interactionContract";
import type { SpriteState } from "./spriteContract";

type DragState = {
  pointerId: number;
  offsetX: number;
  offsetY: number;
  previousScreenX: number;
};

type PetDragBridge = {
  beginPetDrag(offsetX: number, offsetY: number): void;
  endPetDrag(): void;
};

/** Maps pointer gestures to local Codex pet states while the main process follows the cursor. */
export function useCodexPetInteraction(dragBridge: PetDragBridge) {
  const [interactionState, setInteractionState] = useState<SpriteState | null>(null);
  const dragRef = useRef<DragState | null>(null);

  function setNextInteractionState(nextState: SpriteState | null): void {
    setInteractionState((current) => current === nextState ? current : nextState);
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    if (event.button !== 0) return;
    setNextInteractionState(null);
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX,
      offsetY: event.clientY,
      previousScreenX: event.screenX,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    dragBridge.beginPetDrag(event.clientX, event.clientY);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const nextState = petDragState(drag.previousScreenX, event.screenX);
    if (nextState) {
      setNextInteractionState(nextState);
      drag.previousScreenX = event.screenX;
    }
  }

  function onPointerUp(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    dragBridge.endPetDrag();
    setNextInteractionState(petHoverState);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onPointerCancel(): void {
    const drag = dragRef.current;
    dragRef.current = null;
    if (drag) dragBridge.endPetDrag();
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
    pointerHandlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel,
      onPointerEnter,
      onPointerLeave,
    },
  };
}
