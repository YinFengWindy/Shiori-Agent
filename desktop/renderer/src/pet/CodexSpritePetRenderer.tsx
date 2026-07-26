import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { X } from "@phosphor-icons/react";
import { spriteActionDurationMs, spriteCell, spriteFramePosition, spritePlaybackFrameAt, type SpriteState } from "./spriteContract";
import { useCodexPetInteraction } from "./useCodexPetInteraction";
import type { PetBubbleLayout, PetObservationPayload } from "../../../src/observation/types";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
  transientState?: SpriteState | null;
  onTransientFinished?: () => void;
  observation: PetObservationPayload;
  bubbleLayout: PetBubbleLayout;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state, transientState = null, onTransientFinished = noop, observation, bubbleLayout }: CodexSpritePetRendererProps) {
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
  const activeState = transientState ?? observationState ?? interactionState ?? state;
  const activePlaybackFrame = spritePlaybackFrameAt(activeState, frame);

  useEffect(() => {
    setFrame(0);
  }, [activeState]);

  useEffect(() => {
    if (!transientState) return;
    const durationMs = spriteActionDurationMs(transientState);
    if (durationMs <= 0) {
      onTransientFinished();
      return;
    }
    const timer = window.setTimeout(onTransientFinished, durationMs);
    return () => window.clearTimeout(timer);
  }, [onTransientFinished, transientState]);

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
      {observation.bubble ? <PetBubble text={observation.bubble} persistent={observation.persistent} /> : null}
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

function noop(): void {}

function PetBubble({ text, persistent }: { text: string; persistent: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const reportHeight = () => window.miraDesktop.setPetBubbleHeight(element.scrollHeight);
    reportHeight();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(reportHeight);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [persistent, text]);

  return (
    <div
      ref={ref}
      className="pet-bubble"
      role="status"
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
