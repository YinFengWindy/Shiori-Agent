import type { CapturePreferences, CaptureStatus, FaceSample, FaceWorkerReply } from "./contracts";
import { captureResources, createFaceWorker } from "./resources";

type Running = { id: string; worker: Worker; video: HTMLVideoElement; stream: MediaStream | null; timer: ReturnType<typeof setInterval> | null; initTimer: ReturnType<typeof setTimeout> | null; seq: number; acceptedSeq: number; inFlight: boolean; pendingAt: number; videoTime: number };
/** Surface-owned camera and worker resources; pixels never leave this renderer/worker pair. */
export class FaceCaptureSession {
  private current: Running | null = null;
  private lastPhase: CaptureStatus["phase"] = "off";
  constructor(private readonly callbacks: {
    started: (sessionId: string, mirror: boolean) => void;
    sample: (sample: FaceSample) => void;
    stopped: (sessionId: string) => void;
    status: (sessionId: string, phase: CaptureStatus["phase"], error?: string) => void;
    devices: (devices: CaptureStatus["devices"]) => void;
    devicesError: (error: string) => void;
  }) {}
  /** Only an explicit session start dispatched by settings reaches getUserMedia. */
  start(id: string, preferences: CapturePreferences) {
    this.stop();
    try {
      const worker = createFaceWorker(), video = document.createElement("video"); video.muted = true; video.playsInline = true;
      const session: Running = { id, worker, video, stream: null, timer: null, initTimer: null, seq: 0, acceptedSeq: 0, inFlight: false, pendingAt: 0, videoTime: -1 };
      this.current = session; this.callbacks.started(id, preferences.mirror); this.status(session, "starting");
      worker.onmessage = (event: MessageEvent<FaceWorkerReply>) => {
        if (this.current !== session) return;
        const reply = event.data;
        if (reply.kind === "ready" && reply.sessionId === id) {
          if (session.initTimer) clearTimeout(session.initTimer); session.initTimer = null;
          void this.openCamera(session, preferences).catch((error: unknown) => this.fail(session, error));
        } else if (reply.kind === "error" && reply.sessionId === id) this.fail(session, new Error(reply.error));
        else if (reply.kind === "sample" && reply.sample.sessionId === id && reply.sample.seq === session.seq && reply.sample.seq > session.acceptedSeq) {
          session.acceptedSeq = reply.sample.seq; session.inFlight = false;
          this.callbacks.sample(reply.sample);
          this.status(session, reply.sample.face && performance.now() - reply.sample.capturedAt <= 350 ? "tracking" : "no_face");
        }
      };
      worker.onerror = (event) => { event.preventDefault(); this.fail(session, new Error(event.message || "面捕推理初始化失败")); };
      session.initTimer = setTimeout(() => this.fail(session, new Error("面捕模型初始化超时")), 20_000);
      worker.postMessage({ kind: "init", sessionId: id, resources: captureResources() });
    } catch (error) { this.stop(); this.callbacks.status(id, "error", readableError(error)); }
  }
  /** Stops synchronously, including when a permission prompt or image conversion is unresolved. */
  stop(expectedSession?: string) {
    const session = this.current; if (!session || expectedSession && expectedSession !== session.id) return;
    this.current = null;
    if (session.timer) clearInterval(session.timer); if (session.initTimer) clearTimeout(session.initTimer);
    for (const track of session.stream?.getTracks() ?? []) track.stop();
    session.video.pause(); session.video.srcObject = null;
    session.worker.onmessage = null; session.worker.onerror = null; session.worker.terminate();
    this.callbacks.stopped(session.id); this.lastPhase = "off";
  }
  /** Device enumeration never obtains camera permission or starts a stream. */
  async devices() {
    const values = await navigator.mediaDevices.enumerateDevices();
    this.callbacks.devices(values.filter((device) => device.kind === "videoinput").map((device, index) => ({ deviceId: device.deviceId, label: device.label || `摄像头 ${index + 1}` })));
  }
  private async openCamera(session: Running, preferences: CapturePreferences) {
    if (this.current !== session) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 18, max: 20 }, ...(preferences.deviceId ? { deviceId: { exact: preferences.deviceId } } : {}) } });
    if (this.current !== session) { for (const track of stream.getTracks()) track.stop(); return; }
    session.stream = stream;
    for (const track of stream.getVideoTracks()) track.addEventListener("ended", () => this.fail(session, new Error("摄像头连接已结束")), { once: true });
    session.video.srcObject = stream; await session.video.play();
    if (this.current !== session) return;
    this.status(session, "no_face");
    void this.devices().catch((error: unknown) => this.callbacks.devicesError(readableError(error)));
    session.timer = setInterval(() => {
      if (session.inFlight && performance.now() - session.pendingAt > 3_000) { this.fail(session, new Error("面捕推理未响应")); return; }
      void this.frame(session).catch((error: unknown) => this.fail(session, error));
    }, 55);
  }
  private async frame(session: Running) {
    if (this.current !== session || session.inFlight || session.video.readyState < 2 || session.video.currentTime === session.videoTime) return;
    session.inFlight = true; session.pendingAt = performance.now(); session.videoTime = session.video.currentTime;
    const scale = Math.min(1, 640 / session.video.videoWidth, 480 / session.video.videoHeight);
    const bitmap = await createImageBitmap(session.video, { resizeWidth: Math.max(1, Math.round(session.video.videoWidth * scale)), resizeHeight: Math.max(1, Math.round(session.video.videoHeight * scale)) });
    if (this.current !== session) { bitmap.close(); return; }
    try { session.worker.postMessage({ kind: "frame", sessionId: session.id, seq: ++session.seq, capturedAt: session.pendingAt, bitmap }, [bitmap]); }
    catch (error) { bitmap.close(); throw error; }
  }
  private status(session: Running, phase: CaptureStatus["phase"]) { if (this.current !== session || this.lastPhase === phase) return; this.lastPhase = phase; this.callbacks.status(session.id, phase); }
  private fail(session: Running, error: unknown) { if (this.current !== session) return; this.stop(session.id); this.callbacks.status(session.id, "error", readableError(error)); }
}
function readableError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") return "摄像头权限未获允许";
    if (error.name === "NotFoundError" || error.name === "OverconstrainedError") return "所选摄像头不可用";
    if (error.name === "NotReadableError") return "摄像头被占用或无法读取";
  }
  return error instanceof Error ? error.message : String(error);
}
