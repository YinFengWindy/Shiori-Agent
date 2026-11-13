import type { PetPresentationState } from "@shiori-plugin/desktop_pet/provider";
import type { AvatarModel } from "./model";
import { animateScene, createScene, createSceneMotion } from "./scene";
import { paintMouth } from "./mouth";
import { clamp } from "./lids";
import { AvatarWebGL } from "./webgl";
import { FacePoseTracker } from "./facePose";
import type { FaceSample } from "../../capture/contracts";
import { defaultAnimationSettings, type AnimationSettings } from "../../shared/animation";

/** Loads images through img-src grants; no model path is evaluated as code or fetched as a script. */
export function loadAvatarImage(url: string, signal: AbortSignal): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    // Granted shiori-asset images send CORS headers; opt in before assigning src
    // so WebGL can upload pixels from the privileged renderer's other origin.
    image.crossOrigin = "anonymous";
    const cleanup = () => { image.onload = null; image.onerror = null; signal.removeEventListener("abort", aborted); };
    const aborted = () => { cleanup(); image.src = ""; reject(new DOMException("模型加载已取消", "AbortError")); };
    if (signal.aborted) { aborted(); return; }
    signal.addEventListener("abort", aborted, { once: true });
    image.onload = () => { cleanup(); resolve(image); }; image.onerror = () => { cleanup(); reject(new Error("2.5D 模型图片加载失败")); }; image.src = url;
  });
}

/** A surface-local renderer with one RAF and no audio playback ownership. */
export class AvatarRenderer {
  private readonly meshes;
  private readonly motion;
  private readonly mouthCanvas = document.createElement("canvas");
  private readonly gpu: AvatarWebGL;
  private readonly reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  private frameId = 0;
  private disposed = false;
  private previousTime: number | null = null;
  private simulationSeconds = 0;
  private amplitude = 0;
  private mouthValue = 0;
  private playbackId: string | null = null;
  private lastPainted = -1;
  private readonly face = new FacePoseTracker();
  private settings = defaultAnimationSettings();
  private constructor(canvas: HTMLCanvasElement, private readonly model: AvatarModel, private readonly fail: (error: unknown) => void) {
    this.meshes = createScene(model); this.motion = createSceneMotion(this.meshes); this.gpu = new AvatarWebGL(canvas, model.width, model.height);
  }
  /** Completes after all assets and the first neutral WebGL frame are actually drawn. */
  static async create(canvas: HTMLCanvasElement, model: AvatarModel, signal: AbortSignal, fail: (error: unknown) => void): Promise<AvatarRenderer> {
    const renderer = new AvatarRenderer(canvas, model, fail);
    const loading = new AbortController();
    const cancelLoading = () => loading.abort();
    if (signal.aborted) loading.abort(); else signal.addEventListener("abort", cancelLoading, { once: true });
    try {
      const files = new Set(renderer.meshes.flatMap((mesh) => typeof mesh.image === "string" && mesh.part !== "mouth" ? [mesh.image] : []));
      const images = new Map(await Promise.all([...files].map(async (file) => {
        const url = model.images.get(file); if (!url) throw new Error(`模型资源缺失 ${file}`);
        return [file, await loadAvatarImage(url, loading.signal)] as const;
      })));
      if (signal.aborted) throw new DOMException("模型加载已取消", "AbortError");
      paintMouth(renderer.mouthCanvas, model.mouth, 0);
      for (const mesh of renderer.meshes) {
        const image = mesh.part === "mouth" ? renderer.mouthCanvas : typeof mesh.image === "string" ? images.get(mesh.image) : mesh.image;
        if (!image) throw new Error("模型图层资源缺失");
        if (image instanceof HTMLImageElement && (image.naturalWidth !== mesh.layer.w || image.naturalHeight !== mesh.layer.h)) throw new Error(`模型图层尺寸不匹配 ${mesh.layer.name}`);
        renderer.gpu.add(mesh, image);
      }
      renderer.gpu.draw(renderer.meshes, { left: 1, right: 1 });
      renderer.frameId = requestAnimationFrame((time) => renderer.frame(time));
      return renderer;
    } catch (error) { loading.abort(); renderer.dispose(); throw error; }
    finally { signal.removeEventListener("abort", cancelLoading); }
  }
  /** Applies only the desktop's authoritative playback sample; ending closes immediately. */
  audio(audio: PetPresentationState["audio"]) {
    const id = audio?.playback_id ?? null;
    if (id !== this.playbackId || !audio) this.mouthValue = 0;
    this.playbackId = id; this.amplitude = audio ? audio.amplitude : 0;
  }
  /** Applies package preferences in place, retaining textures, pose and spring state. */
  tune(settings: AnimationSettings) { this.settings = settings; }
  /** Camera samples are local to this renderer and one explicitly started session. */
  startFaceSession(sessionId: string, mirror: boolean) { this.face.start(sessionId, mirror); }
  /** Retires late frames as soon as the camera or its lease stops. */
  stopFaceSession(sessionId: string) { this.face.stop(sessionId); }
  /** Accepts ordered samples; stale inference cannot drive a new session. */
  faceSample(sample: FaceSample) { this.face.accept(sample); }
  /** Replaces only the in-memory neutral posture. */
  calibrateFace() { return this.face.calibrate(); }
  /** Stops future frames and frees textures/buffers, including after context loss. */
  dispose() { if (this.disposed) return; this.disposed = true; cancelAnimationFrame(this.frameId); this.gpu.dispose(); this.mouthCanvas.width = 0; this.mouthCanvas.height = 0; }
  private frame(time: number) {
    if (this.disposed) return;
    try {
      const elapsed = this.previousTime === null ? 0 : Math.min(0.05, Math.max(0, (time - this.previousTime) / 1000)); this.previousTime = time; this.simulationSeconds += elapsed;
      const face = this.face.sample(time, elapsed);
      // Ownership follows the real playback ID, so a silent TTS segment still
      // suppresses camera mouth motion while head and eyes continue tracking.
      const mouthTarget = this.playbackId !== null ? clamp(this.amplitude * 4 * this.settings.voiceMouthGain) : clamp((face?.mouth ?? 0) * this.settings.faceMouthGain);
      this.mouthValue += (mouthTarget - this.mouthValue) * (1 - Math.exp(-elapsed / (mouthTarget > this.mouthValue ? 0.035 : 0.06)));
      if (this.mouthValue < 0.003) this.mouthValue = 0;
      const openness = animateScene(this.model, this.meshes, this.motion, this.simulationSeconds, elapsed, this.reducedMotion.matches, this.mouthValue, face, this.settings);
      if (Math.abs(this.mouthValue - this.lastPainted) > 0.001) {
        paintMouth(this.mouthCanvas, this.model.mouth, this.mouthValue); this.lastPainted = this.mouthValue;
        const index = this.meshes.findIndex((mesh) => mesh.part === "mouth"); this.gpu.mouth(index, this.mouthCanvas);
      }
      this.gpu.draw(this.meshes, openness);
      this.frameId = requestAnimationFrame((next) => this.frame(next));
    } catch (error) { this.dispose(); this.fail(error); }
  }
}
