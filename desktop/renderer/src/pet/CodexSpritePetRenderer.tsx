import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { X } from "@phosphor-icons/react";
import { spriteCell, spriteFramePosition, spritePlaybackFrameAt, type SpriteState } from "./spriteContract";
import { useCodexPetInteraction } from "./useCodexPetInteraction";
import type { PetBubbleLayout, PetObservationPayload } from "../../../src/observation/types";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
  observation: PetObservationPayload;
  bubbleLayout: PetBubbleLayout;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state, observation, bubbleLayout }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
  const { interactionState, isDragging, pointerHandlers } = useCodexPetInteraction(
    typeof window === "undefined" ? null : window.miraDesktop,
  );
  const observationState: SpriteState | null = observation.status === "reviewing"
    ? "review"
    : observation.status === "paused"
      ? "waiting"
      : observation.status === "failed"
        ? "failed"
        : null;
  const activeState = observationState ?? interactionState ?? state;
  const activePlaybackFrame = spritePlaybackFrameAt(activeState, frame);

  useEffect(() => {
    setFrame(0);
  }, [activeState]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFrame((current) => current + 1);
    }, activePlaybackFrame.duration);
    return () => window.clearTimeout(timer);
  }, [activePlaybackFrame.duration, activeState, frame]);

  useEffect(() => {
    if (!observation.bubble) window.miraDesktop.setPetBubbleHeight(0);
  }, [observation.bubble]);

  const surfaceClass = observation.bubble
    ? `pet-surface pet-bubble-${bubbleLayout.placement}`
    : "pet-surface";

  return (
    <div className={surfaceClass}>
      {observation.bubble ? <PetBubble text={observation.bubble} persistent={observation.persistent} maxHeight={bubbleLayout.height} /> : null}
      <div
        aria-label="桌宠"
        className={isDragging ? "pet-drag-region pet-dragging" : "pet-drag-region"}
        {...pointerHandlers}
        onLostPointerCapture={pointerHandlers.onPointerCancel}
        onContextMenu={(event) => {
          event.preventDefault();
          window.miraDesktop.openPetMenu();
        }}
        style={{
          width: spriteCell.width,
          height: spriteCell.height,
          backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`,
          backgroundPosition: spriteFramePosition(activePlaybackFrame.state, activePlaybackFrame.frame),
          backgroundRepeat: "no-repeat",
          touchAction: "none",
        }}
      />
    </div>
  );
}

function PetBubble({ text, persistent, maxHeight }: { text: string; persistent: boolean; maxHeight: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const reportHeight = () => window.miraDesktop.setPetBubbleHeight(element.scrollHeight);
    reportHeight();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(reportHeight);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [maxHeight, persistent, text]);

  return (
    <div
      ref={ref}
      className="pet-bubble"
      role="status"
      style={maxHeight ? { maxHeight } : undefined}
    >
      <span>{text}</span>
      {persistent ? (
        <button
          type="button"
          className="pet-bubble-dismiss"
          aria-label="关闭消息"
          title="关闭消息"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={() => {
            void window.miraDesktop.dismissPetObservationBubble();
          }}
        >
          <X size={12} weight="bold" />
        </button>
      ) : null}
    </div>
  );
}
