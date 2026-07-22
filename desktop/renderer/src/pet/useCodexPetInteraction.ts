import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { petDragState, petHoverState } from "./interactionContract";
import type { SpriteState } from "./spriteContract";

type DragState = {
  pointerId: number;
  offsetX: number;
  offsetY: number;
  previousScreenX: number;
};

type PetPosition = { x: number; y: number };

/** Maps pointer gestures to Codex pet states and batches native window moves to one per frame. */
export function useCodexPetInteraction(onMove: (x: number, y: number) => void) {
  const [interactionState, setInteractionState] = useState<SpriteState | null>(null);
  const moveRef = useRef(onMove);
  const dragRef = useRef<DragState | null>(null);
  const pendingPositionRef = useRef<PetPosition | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    moveRef.current = onMove;
  }, [onMove]);

  useEffect(() => () => {
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
    }
  }, []);

  function setNextInteractionState(nextState: SpriteState | null): void {
    setInteractionState((current) => current === nextState ? current : nextState);
  }

  function flushPendingMove(): void {
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    const position = pendingPositionRef.current;
    pendingPositionRef.current = null;
    if (position) moveRef.current(position.x, position.y);
  }

  function queueMove(position: PetPosition): void {
    pendingPositionRef.current = position;
    if (animationFrameRef.current !== null) return;
    animationFrameRef.current = window.requestAnimationFrame(() => {
      animationFrameRef.current = null;
      const nextPosition = pendingPositionRef.current;
      pendingPositionRef.current = null;
      if (nextPosition) moveRef.current(nextPosition.x, nextPosition.y);
    });
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
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const nextState = petDragState(drag.previousScreenX, event.screenX);
    if (nextState) {
      setNextInteractionState(nextState);
      drag.previousScreenX = event.screenX;
    }
    queueMove({ x: event.screenX - drag.offsetX, y: event.screenY - drag.offsetY });
  }

  function onPointerUp(event: ReactPointerEvent<HTMLDivElement>): void {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    flushPendingMove();
    setNextInteractionState(petHoverState);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onPointerCancel(): void {
    dragRef.current = null;
    flushPendingMove();
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
