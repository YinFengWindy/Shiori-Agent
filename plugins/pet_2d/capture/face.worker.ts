import { FaceLandmarker } from "@mediapipe/tasks-vision";
import type { FaceLandmarkerResult } from "@mediapipe/tasks-vision";
import type { FaceSample, FaceWorkerReply, FaceWorkerRequest } from "./contracts";

let landmarker: FaceLandmarker | null = null;
let sessionId = "";
const send = (value: FaceWorkerReply) => postMessage(value);

// This is bundled as a classic IIFE worker. Resource URLs arrive from its
// trusted parent; neither import.meta nor any model-supplied script is used.
globalThis.onmessage = (event: MessageEvent<FaceWorkerRequest>) => {
  const request = event.data;
  if (request.kind === "init") {
    sessionId = request.sessionId;
    void FaceLandmarker.createFromOptions({ wasmLoaderPath: request.resources.wasmLoaderPath, wasmBinaryPath: request.resources.wasmBinaryPath }, {
      baseOptions: { modelAssetPath: request.resources.modelURL, delegate: "CPU" }, runningMode: "VIDEO", numFaces: 1,
      outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
    }).then((next) => {
      if (sessionId !== request.sessionId) { next.close(); return; }
      landmarker?.close(); landmarker = next; send({ kind: "ready", sessionId });
    }).catch((error: unknown) => send({ kind: "error", sessionId: request.sessionId, error: error instanceof Error ? error.message : String(error) }));
    return;
  }
  if (request.kind !== "frame") return;
  try {
    if (!landmarker || request.sessionId !== sessionId) return;
    const result = landmarker.detectForVideo(request.bitmap, request.capturedAt);
    send({ kind: "sample", sample: { sessionId, seq: request.seq, capturedAt: request.capturedAt, face: readFace(result) } });
  } catch (error) { send({ kind: "error", sessionId: request.sessionId, error: error instanceof Error ? error.message : String(error) }); }
  finally { request.bitmap.close(); }
};

function readFace(result: FaceLandmarkerResult): FaceSample["face"] {
  if (!result.faceLandmarks.length) return null;
  const matrix = result.facialTransformationMatrixes[0];
  if (!matrix || matrix.rows !== 4 || matrix.columns !== 4 || matrix.data.length !== 16) throw new Error("面捕姿态矩阵无效");
  const m = matrix.data, scaleX = Math.hypot(m[0], m[1], m[2]), scaleY = Math.hypot(m[4], m[5], m[6]), scaleZ = Math.hypot(m[8], m[9], m[10]);
  if (Math.min(scaleX, scaleY, scaleZ) <= 0 || !m.every(Number.isFinite)) throw new Error("面捕姿态数值无效");
  // MediaPipe matrix_data.proto defaults to COLUMN_MAJOR; normalize scale before
  // Euler extraction (mediapipe/framework/formats/matrix_data.proto and matrix.cc).
  const yaw = Math.asin(Math.max(-1, Math.min(1, -m[2] / scaleX))), pitch = Math.atan2(m[6] / scaleY, m[10] / scaleZ), roll = Math.atan2(m[1] / scaleX, m[0] / scaleX);
  const scores = new Map(result.faceBlendshapes[0]?.categories.map((category) => [category.categoryName, category.score]));
  return { yaw, pitch, roll, blinkLeft: scores.get("eyeBlinkLeft") ?? 0, blinkRight: scores.get("eyeBlinkRight") ?? 0, mouth: scores.get("jawOpen") ?? 0 };
}
