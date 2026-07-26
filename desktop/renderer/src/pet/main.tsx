import { createRoot } from "react-dom/client";
import { useCallback, useEffect, useState } from "react";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";
import { spriteAnimations, type SpriteState } from "./spriteContract";
import { usePetActivityState } from "./usePetActivityState";
import type { PetBubbleLayout, PetObservationPayload } from "../../../src/observation/types";
import type { VoiceStatePayload } from "../../../src/shared";
import "./styles.css";

type PetPackagePayload = { spritesheetUrl: string };
type PetPayload = { package: PetPackagePayload; state: SpriteState };
const defaultObservation: PetObservationPayload = {
  status: "off",
  enabled: false,
  bubble: "",
  persistent: false,
};
const defaultBubbleLayout: PetBubbleLayout = { placement: "below", height: 0 };
const defaultVoice: VoiceStatePayload = { status: "idle" };

function isSpriteState(value: unknown): value is SpriteState {
  return typeof value === "string" && value in spriteAnimations;
}

function isPetPayload(value: unknown): value is PetPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as { package?: { spritesheetUrl?: unknown }; state?: unknown };
  return typeof payload.package?.spritesheetUrl === "string" && isSpriteState(payload.state);
}

function isObservationStatus(value: unknown): value is PetObservationPayload["status"] {
  return value === "off"
    || value === "observing"
    || value === "reviewing"
    || value === "paused"
    || value === "failed";
}

function isBubbleLayout(value: unknown): value is PetBubbleLayout {
  if (!value || typeof value !== "object") return false;
  const layout = value as Partial<PetBubbleLayout>;
  return (layout.placement === "above" || layout.placement === "below")
    && typeof layout.height === "number"
    && Number.isFinite(layout.height)
    && layout.height >= 0;
}

function DesktopPetSurface() {
  const [payload, setPayload] = useState<PetPayload | null>(null);
  const [state, setState] = useState<SpriteState>("idle");
  const [transientState, setTransientState] = useState<SpriteState | null>(null);
  const [observation, setObservation] = useState<PetObservationPayload>(defaultObservation);
  const [bubbleLayout, setBubbleLayout] = useState<PetBubbleLayout>(defaultBubbleLayout);
  const [voice, setVoice] = useState<VoiceStatePayload>(defaultVoice);
  const activityState = usePetActivityState(state);
  const onTransientFinished = useCallback(() => setTransientState(null), []);

  useEffect(() => {
    const onLoad = (_event: unknown, next: unknown) => {
      if (!isPetPayload(next)) return;
      setPayload(next);
      setState(next.state);
      setTransientState(null);
    };
    const onPlay = (_event: unknown, next: unknown) => {
      if (!next || typeof next !== "object" || !isSpriteState((next as { state?: unknown }).state)) return;
      const value = next as { state: SpriteState; transient?: unknown };
      if (value.transient === true) {
        setTransientState(value.state);
        return;
      }
      setState(value.state);
      setTransientState(null);
    };
    window.miraDesktop.onPetLoad(onLoad);
    window.miraDesktop.onPetPlay(onPlay);
    const onObservation = (_event: unknown, next: unknown) => {
      if (!next || typeof next !== "object") return;
      const value = next as Partial<PetObservationPayload>;
      if (!isObservationStatus(value.status) || typeof value.enabled !== "boolean") return;
      setObservation({
        status: value.status,
        enabled: value.enabled,
        bubble: typeof value.bubble === "string" ? value.bubble : "",
        persistent: value.persistent === true,
      });
    };
    window.miraDesktop.onPetObservation(onObservation);
    const onBubbleLayout = (_event: unknown, next: unknown) => {
      if (!isBubbleLayout(next)) return;
      setBubbleLayout((current) => (
        current.placement === next.placement && current.height === next.height
          ? current
          : next
      ));
    };
    window.miraDesktop.onPetBubbleLayout(onBubbleLayout);
    const unsubscribeVoice = window.miraDesktop.onVoiceState((next) => {
      if (isVoiceState(next)) setVoice(next);
    });
    window.miraDesktop.petRendererReady();
    return () => {
      window.miraDesktop.offPetLoad(onLoad);
      window.miraDesktop.offPetPlay(onPlay);
      window.miraDesktop.offPetObservation(onObservation);
      window.miraDesktop.offPetBubbleLayout(onBubbleLayout);
      unsubscribeVoice();
    };
  }, []);

  if (!payload) return null;
  return (
    <CodexSpritePetRenderer
      spritesheetUrl={payload.package.spritesheetUrl}
      state={activityState}
      transientState={transientState}
      onTransientFinished={onTransientFinished}
      observation={observation}
      bubbleLayout={bubbleLayout}
      voice={voice}
    />
  );
}

function isVoiceState(value: unknown): value is VoiceStatePayload {
  if (!value || typeof value !== "object") return false;
  const status = (value as { status?: unknown }).status;
  return status === "idle"
    || status === "press_pending"
    || status === "dragging"
    || status === "recording"
    || status === "transcribing"
    || status === "sending"
    || status === "waiting_reply"
    || status === "speaking_prepare"
    || status === "speaking"
    || status === "finish_current_sentence_then_idle"
    || status === "error";
}

createRoot(document.getElementById("root") as HTMLElement).render(<DesktopPetSurface />);
