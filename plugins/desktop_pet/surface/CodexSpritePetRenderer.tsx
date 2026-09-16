import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { X } from "@phosphor-icons/react";
import { spriteActionDurationMs, spriteCell, spriteFramePosition, spritePlaybackFrameAt, type SpriteState } from "./spriteContract";
import { useCodexPetInteraction } from "./useCodexPetInteraction";
import { noPetBubble, type PetBubblePlacement } from "./bubbleExtension";
import type { SurfaceHandle } from "../../../apps/desktop/renderer/src/surface/pluginSurfaceRegistry";
import type { PetReplyBubble } from "../shared/replyBubble";
import type { VoiceStatePayload } from "../../../apps/desktop/src/bridge/shared";

type CodexSpritePetRendererProps = {
  /** Opens the owning plugin menu through its injected communication client. */
  onContextMenu?: () => void;
  spritesheetUrl: string;
  state: SpriteState;
  transientState?: SpriteState | null;
  onTransientFinished?: () => void;
  reply: PetReplyBubble;
  /** Requests dismissal through this plugin’s own backend namespace. */
  onDismissBubble?: () => void;
  /** Which side the bubble occupies; chosen by this plugin, not by the host. */
  bubbleLayout?: PetBubblePlacement;
  voice?: VoiceStatePayload;
  /** The window this pet is rendering inside; null in a plain render test. */
  surface?: SurfaceHandle | null;
  /** Reports the measured bubble height so the surface can be resized around it. */
  onBubbleHeight?: (height: number) => void;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ onContextMenu = noop, spritesheetUrl, state, transientState = null, onTransientFinished = noop, reply, onDismissBubble = noop, bubbleLayout = noPetBubble, voice = { status: "idle" }, surface = null, onBubbleHeight = noop }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
  const { interactionState, isDragging, pointerHandlers } = useCodexPetInteraction(
    surface,
    typeof window === "undefined" ? null : window.miraDesktop,
  );
  const replyState: SpriteState | null = reply.paused ? "waiting" : null;
  const voicePlaybackState: SpriteState | null = voice.status === "recording"
    || voice.status === "transcribing"
    || voice.status === "sending"
    || voice.status === "waiting_reply"
    || voice.status === "speaking_prepare"
    ? "waiting"
    : null;
  const voiceBubble = voice.status === "recording"
    ? "我在听"
    : voice.status === "transcribing" || voice.status === "sending" || voice.status === "waiting_reply" || voice.status === "speaking_prepare"
      ? "正在理解"
      : voice.status === "error"
        ? voice.message || "没听清，再试一次"
        : "";
  const bubbleText = voiceBubble || reply.text;
  const activeState = transientState ?? replyState ?? interactionState ?? voicePlaybackState ?? state;
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
    if (!bubbleText) onBubbleHeight(0);
  }, [bubbleText, onBubbleHeight]);

  const surfaceClass = bubbleText
    ? `pet-surface pet-bubble-${bubbleLayout.placement}`
    : "pet-surface";

  return (
    <div className={surfaceClass}>
      {bubbleText ? <PetBubble text={bubbleText} persistent={!voiceBubble && reply.persistent} onHeight={onBubbleHeight} onDismiss={onDismissBubble} /> : null}
      <div
        aria-label="桌宠"
        className={isDragging ? "pet-drag-region pet-dragging" : "pet-drag-region"}
        {...pointerHandlers}
        onLostPointerCapture={pointerHandlers.onPointerCancel}
        onContextMenu={(event) => {
          event.preventDefault();
          onContextMenu();
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

function PetBubble({ text, persistent, onHeight, onDismiss }: { text: string; persistent: boolean; onHeight: (height: number) => void; onDismiss: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const reportHeight = () => onHeight(element.scrollHeight);
    reportHeight();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(reportHeight);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [onHeight, persistent, text]);

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
          onClick={onDismiss}
        >
          <X size={12} weight="bold" />
        </button>
      ) : null}
    </div>
  );
}
