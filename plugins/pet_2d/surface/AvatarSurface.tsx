import React, { useEffect, useRef, useState } from "react";
import { useLatestRef, type PluginSurfaceComponentProps, type SurfaceHandle } from "@yinfengwindy/shiori-sdk";
import { PetShell, readPresentationIdentity, readPresentationState, type PetPresentationState } from "@yinfengwindy/shiori-pet";
import { finite, parseAvatarModel, record, type AvatarModel } from "./runtime/model";
import { AvatarRenderer } from "./runtime/renderer";
import { useFaceCapture } from "../capture/useFaceCapture";
import { useAnimationSettings } from "./useAnimationSettings";

type Loaded = { leaseId: string; body: { width: number; height: number }; model: AvatarModel; state: PetPresentationState };
/** A lease loads once; subsequent audio/reply snapshots keep its mesh and GPU state intact. */
export function AvatarSurface({ surface }: PluginSurfaceComponentProps) {
  const [load, setLoad] = useState<Loaded | null>(null);
  const latestLoad = useLatestRef(load);
  useEffect(() => {
    const unsubscribe = surface.onState((value) => {
      const identity = readPresentationIdentity(value); if (!identity) return;
      try {
        const payload = record(value), state = readPresentationState(payload.state); if (!state) throw new Error("2.5D 展示状态无效");
        const current = latestLoad.current;
        if (current?.leaseId === identity.lease_id) { setLoad({ ...current, state }); return; }
        const body = record(payload.body);
        setLoad({ leaseId: identity.lease_id, body: { width: finite(body.width), height: finite(body.height) }, model: parseAvatarModel(payload.model_data), state });
      } catch (error) { surface.postToBackground({ kind: "model.failed", lease_id: identity.lease_id, error: error instanceof Error ? error.message : String(error) }); }
    });
    surface.ready(); return unsubscribe;
  }, [latestLoad, surface]);
  if (!load) return null;
  return <PetShell surface={surface} body={load.body} state={load.state}>{() => <AvatarCanvas key={load.leaseId} load={load} surface={surface} />}</PetShell>;
}

function AvatarCanvas({ load, surface }: { load: Loaded; surface: SurfaceHandle }) {
  const canvas = useRef<HTMLCanvasElement>(null), renderer = useRef<AvatarRenderer | null>(null);
  const latestState = useLatestRef(load.state);
  useFaceCapture(surface, load.leaseId, renderer);
  useAnimationSettings(surface, load.leaseId, renderer);
  useEffect(() => {
    const element = canvas.current; if (!element) return;
    const abort = new AbortController();
    const failed = (error: unknown) => { if (!abort.signal.aborted) surface.postToBackground({ kind: "model.failed", lease_id: load.leaseId, error: error instanceof Error ? error.message : String(error) }); };
    const lost = (event: Event) => { event.preventDefault(); renderer.current?.dispose(); failed(new Error("2.5D WebGL 资源已失效")); };
    element.addEventListener("webglcontextlost", lost);
    void AvatarRenderer.create(element, load.model, abort.signal, failed).then((instance) => {
      if (abort.signal.aborted) { instance.dispose(); return; }
      renderer.current = instance; instance.audio(latestState.current.audio);
      surface.postToBackground({ kind: "model.ready", lease_id: load.leaseId });
    }).catch(failed);
    return () => { abort.abort(); element.removeEventListener("webglcontextlost", lost); renderer.current?.dispose(); renderer.current = null; };
  }, [load.leaseId, load.model, latestState, surface]);
  useEffect(() => renderer.current?.audio(load.state.audio), [load.state.audio]);
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  return <canvas ref={canvas} width={Math.round(load.body.width * ratio)} height={Math.round(load.body.height * ratio)} aria-label="2.5D 角色" style={{ width: load.body.width, height: load.body.height, display: "block", pointerEvents: "none" }} />;
}
