import { useEffect, useState } from "react";
import { Eye, EyeSlash, CircleNotch, PauseCircle, WarningCircle, X } from "@phosphor-icons/react";
import { spriteCell, spriteFramePosition, spritePlaybackFrameAt, type SpriteState } from "./spriteContract";
import { useCodexPetInteraction } from "./useCodexPetInteraction";
import type { PetObservationPayload } from "../../../src/observation/types";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
  observation: PetObservationPayload;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state, observation }: CodexSpritePetRendererProps) {
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

  return (
    <div className="pet-surface">
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
      <PetObservationToggle observation={observation} disabled={isDragging} />
    </div>
  );
}

function PetObservationToggle({ observation, disabled }: { observation: PetObservationPayload; disabled: boolean }) {
  const Icon = observation.status === "failed"
    ? WarningCircle
    : observation.status === "paused"
      ? PauseCircle
      : observation.status === "reviewing"
        ? CircleNotch
        : observation.enabled
          ? Eye
          : EyeSlash;
  const label = observation.status === "failed"
    ? "屏幕观察失败"
    : observation.status === "paused"
      ? "屏幕观察已暂停"
      : observation.status === "reviewing"
        ? "正在观察主屏幕"
        : observation.enabled
          ? "关闭屏幕观察"
          : "开启屏幕观察";
  return (
    <button
      type="button"
      className={`pet-observation-toggle pet-observation-${observation.status}`}
      aria-label={label}
      title={label}
      disabled={disabled}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        void window.miraDesktop.togglePetObservation();
      }}
    >
      <Icon size={16} weight="bold" />
    </button>
  );
}

function PetBubble({ text, persistent }: { text: string; persistent: boolean }) {
  return (
    <div className="pet-bubble" role="status">
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
