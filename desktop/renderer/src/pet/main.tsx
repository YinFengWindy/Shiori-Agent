import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";
import { spriteAnimations, type SpriteState } from "./spriteContract";
import { usePetActivityState } from "./usePetActivityState";
import "./styles.css";

type PetPackagePayload = { spritesheetUrl: string };
type PetPayload = { package: PetPackagePayload; state: SpriteState };

function isSpriteState(value: unknown): value is SpriteState {
  return typeof value === "string" && value in spriteAnimations;
}

function isPetPayload(value: unknown): value is PetPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as { package?: { spritesheetUrl?: unknown }; state?: unknown };
  return typeof payload.package?.spritesheetUrl === "string" && isSpriteState(payload.state);
}

function DesktopPetSurface() {
  const [payload, setPayload] = useState<PetPayload | null>(null);
  const [state, setState] = useState<SpriteState>("idle");
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
    return () => {
      window.miraDesktop.offPetLoad(onLoad);
      window.miraDesktop.offPetPlay(onPlay);
    };
  }, []);

  if (!payload) return null;
  return <CodexSpritePetRenderer spritesheetUrl={payload.package.spritesheetUrl} state={activityState} />;
}

createRoot(document.getElementById("root") as HTMLElement).render(<DesktopPetSurface />);
