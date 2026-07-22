import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { petDragState, petHoverState } from "./interactionContract";
import type { SpriteState } from "./spriteContract";

type DragState = {
  pointerId: number;
  previousScreenX: number;
};

/** Maps pointer gestures to local Codex pet states while native input moves the window. */
export function useCodexPetInteraction() {
  const [interactionState, setInteractionState] = useState<SpriteState | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<DragState | null>(null);

  function setNextInteractionState(nextState: SpriteState | null): void {
    setInteractionState((current) => current === nextState ? current : nextState);
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    if (event.button !== 0) return;
    setNextInteractionState(null);
    setIsDragging(true);
    dragRef.current = {
      pointerId: event.pointerId,
      previousScreenX: event.screenX,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
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
    setIsDragging(false);
    setNextInteractionState(petHoverState);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onPointerCancel(): void {
    const drag = dragRef.current;
    dragRef.current = null;
    if (drag) setIsDragging(false);
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
    cursor: isDragging ? "grabbing" : "default",
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
