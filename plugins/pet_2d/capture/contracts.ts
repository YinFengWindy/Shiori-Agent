/** Device preference survives restart; enabling capture never does. */
export type CapturePreferences = { deviceId: string; mirror: boolean };
/** User-facing capture state, containing no image or biometric landmark history. */
export type CaptureStatus = { enabled: boolean; available: boolean; preferences: CapturePreferences; phase: "off" | "paused" | "starting" | "tracking" | "no_face" | "error"; error: string; devices: { deviceId: string; label: string }[] };
/** An unpersisted pose result from exactly one frame and camera session. */
export type FaceSample = { sessionId: string; seq: number; capturedAt: number; face: { yaw: number; pitch: number; roll: number; blinkLeft: number; blinkRight: number; mouth: number } | null };
/** Trusted static build resources used by the classic inference worker. */
export type FaceResources = { wasmLoaderPath: string; wasmBinaryPath: string; modelURL: string };
/** Transfer-only worker requests; a frame has one owner at a time. */
export type FaceWorkerRequest = { kind: "init"; sessionId: string; resources: FaceResources } | { kind: "frame"; sessionId: string; seq: number; capturedAt: number; bitmap: ImageBitmap };
/** Worker completion carries identity on both successful and failed work. */
export type FaceWorkerReply = { kind: "ready"; sessionId: string } | { kind: "sample"; sample: FaceSample } | { kind: "error"; sessionId: string; error: string };
/** Provider-private instructions targeted at one shown surface lease. */
export type CaptureCommand = { kind: "capture.start"; leaseId: string; sessionId: string; preferences: CapturePreferences } | { kind: "capture.stop"; leaseId: string; sessionId: string; requestId: string } | { kind: "capture.devices"; leaseId: string } | { kind: "capture.calibrate"; leaseId: string; sessionId: string };
