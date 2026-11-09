import wasmLoader from "@mediapipe/tasks-vision/vision_wasm_internal.js?url";
import wasmBinary from "@mediapipe/tasks-vision/vision_wasm_internal.wasm?url";
import model from "../assets/face_landmarker.task?url";
import workerURL from "./face.worker.ts?worker&url";
import type { FaceResources } from "./contracts";

/** URLs are emitted by the plugin build, never read from imported character data. */
export function captureResources(): FaceResources { return { wasmLoaderPath: new URL(wasmLoader, import.meta.url).href, wasmBinaryPath: new URL(wasmBinary, import.meta.url).href, modelURL: new URL(model, import.meta.url).href }; }
/** A classic bootstrap permits importScripts inside MediaPipe's WASM loader. */
export function createFaceWorker(): Worker {
  const entry = new URL(workerURL, import.meta.url).href;
  const bootstrap = URL.createObjectURL(new Blob([`importScripts(${JSON.stringify(entry)});`], { type: "text/javascript" }));
  try { return new Worker(bootstrap); } finally { URL.revokeObjectURL(bootstrap); }
}
