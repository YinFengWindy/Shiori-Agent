import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";
import { spriteAnimations, type SpriteState } from "./spriteContract";
import { usePetActivityState } from "./usePetActivityState";
import type { PetBubbleLayout, PetObservationPayload } from "../../../src/observation/types";
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
  const [observation, setObservation] = useState<PetObservationPayload>(defaultObservation);
  const [bubbleLayout, setBubbleLayout] = useState<PetBubbleLayout>(defaultBubbleLayout);
  const activityState = usePetActivityState(state);

  useEffect(() => {
    const onLoad = (_event: unknown, next: unknown) => {
      if (!isPetPayload(next)) return;
      setPayload(next);
      setState(next.state);
    };
    const onPlay = (_event: unknown, next: unknown) => {
      if (!next || typeof next !== "object" || !isSpriteState((next as { state?: unknown }).state)) return;
      setState((next as { state: SpriteState }).state);
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
    window.miraDesktop.petRendererReady();
    return () => {
      window.miraDesktop.offPetLoad(onLoad);
      window.miraDesktop.offPetPlay(onPlay);
      window.miraDesktop.offPetObservation(onObservation);
      window.miraDesktop.offPetBubbleLayout(onBubbleLayout);
    };
  }, []);

  if (!payload) return null;
  return <CodexSpritePetRenderer spritesheetUrl={payload.package.spritesheetUrl} state={activityState} observation={observation} bubbleLayout={bubbleLayout} />;
}

createRoot(document.getElementById("root") as HTMLElement).render(<DesktopPetSurface />);
