import React from "react";
import { useCallback, useEffect, useState } from "react";
import type { PluginSurfaceComponentProps } from "@yinfengwindy/shiori-sdk";
import { PetShell } from "@shiori-plugin/desktop_pet/provider";
import { readSpritePresentation, readSpriteState, type SpritePresentation } from "../shared/presentation";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";
import { usePetActivityState } from "./usePetActivityState";
import type { SpriteState } from "./spriteContract";

/** Restores retained model/state and reports real asset load before the window can be shown. */
export function SpriteSurface({ surface }: PluginSurfaceComponentProps) {
  const [load, setLoad] = useState<SpritePresentation | null>(null);
  const [transient, setTransient] = useState<SpriteState | null>(null);
  const finishTransient = useCallback(() => setTransient(null), []);
  const activity = usePetActivityState(surface, "idle");
  useEffect(() => {
    const offState = surface.onState((value) => { const next = readSpritePresentation(value); if (next) setLoad(next); });
    const offMessage = surface.onMessage((value) => {
      if (!value || typeof value !== "object" || !("state" in value)) return;
      const next = readSpriteState(value.state);
      if (next) setTransient(next);
    });
    surface.ready();
    return () => { offState(); offMessage(); };
  }, [surface]);
  if (!load) return null;
  const voiceWaiting = ["recording", "transcribing", "sending", "waiting_reply", "speaking_prepare"].includes(load.state.voice.status);
  return <PetShell surface={surface} body={load.body} state={load.state}>
    {(pointer) => <CodexSpritePetRenderer key={load.lease_id} spritesheetUrl={load.spritesheetUrl}
      state={load.state.reply.paused || voiceWaiting ? "waiting" : pointer === "hover" ? "jumping" : pointer === "left" ? "running-left" : pointer === "right" ? "running-right" : activity}
      transientState={transient} onTransientFinished={finishTransient}
      onLoaded={() => surface.postToBackground({ kind: "model.ready", lease_id: load.lease_id })}
      onFailed={() => surface.postToBackground({ kind: "model.failed", lease_id: load.lease_id })} />}
  </PetShell>;
}
