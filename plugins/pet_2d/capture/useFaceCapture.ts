import { useEffect, type RefObject } from "react";
import type { SurfaceHandle } from "@yinfengwindy/shiori-sdk";
import { isRecord } from "@yinfengwindy/shiori-pet";
import type { AvatarRenderer } from "../surface/runtime/renderer";
import { FaceCaptureSession } from "./session";

/** Connects camera ownership to this exact rendered lease without sending frames to the background. */
export function useFaceCapture(surface: SurfaceHandle, leaseId: string, renderer: RefObject<AvatarRenderer | null>) {
  useEffect(() => {
    let disposed = false, sessionId: string | null = null;
    const report = (value: Record<string, unknown>) => { if (!disposed) surface.postToBackground({ ...value, leaseId }); };
    const capture = new FaceCaptureSession({
      started: (id, mirror) => { sessionId = id; renderer.current?.startFaceSession(id, mirror); },
      sample: (sample) => renderer.current?.faceSample(sample),
      stopped: (id) => { renderer.current?.stopFaceSession(id); if (sessionId === id) sessionId = null; },
      status: (id, phase, error) => report({ kind: "capture.status", sessionId: id, phase, ...(error ? { error } : {}) }),
      devices: (devices) => report({ kind: "capture.devices", devices }),
      devicesError: (error) => report({ kind: "capture.devices.error", error }),
    });
    const enumerate = () => { void capture.devices().catch((error: unknown) => report({ kind: "capture.devices.error", error: error instanceof Error ? error.message : String(error) })); };
    const unsubscribe = surface.onMessage((value) => {
      if (!isRecord(value) || value.leaseId !== leaseId) return;
      if (value.kind === "capture.start" && typeof value.sessionId === "string" && isRecord(value.preferences) && typeof value.preferences.deviceId === "string" && typeof value.preferences.mirror === "boolean") capture.start(value.sessionId, { deviceId: value.preferences.deviceId, mirror: value.preferences.mirror });
      else if (value.kind === "capture.stop" && typeof value.sessionId === "string") { capture.stop(value.sessionId); report({ kind: "capture.stopped", sessionId: value.sessionId, requestId: value.requestId }); }
      else if (value.kind === "capture.devices") enumerate();
      else if (value.kind === "capture.calibrate" && value.sessionId === sessionId) report({ kind: "capture.calibrated", sessionId, ok: renderer.current?.calibrateFace() ?? false });
    });
    const hidden = () => {
      if (!document.hidden || !sessionId) return;
      const previous = sessionId; capture.stop(previous);
      report({ kind: "capture.status", sessionId: previous, phase: "error", error: "窗口已隐藏，面捕已停止" });
    };
    const closing = () => capture.stop();
    document.addEventListener("visibilitychange", hidden); window.addEventListener("pagehide", closing);
    return () => { disposed = true; unsubscribe(); document.removeEventListener("visibilitychange", hidden); window.removeEventListener("pagehide", closing); capture.stop(); };
  }, [leaseId, renderer, surface]);
}
