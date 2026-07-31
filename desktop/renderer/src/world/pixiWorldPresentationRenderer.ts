import {
  Application,
  Container,
  Graphics,
  Sprite,
  Texture,
  type Ticker,
} from "pixi.js";
import type { PresentationCue } from "./presentationProtocol";
import { cuePayloadItems, normalizedCharacterPosition, numericCueValue, stringCueValue } from "./pixiCuePayload";
import { loadPixiWorldTexture } from "./pixiWorldAssetLoader";
import { WorldAssetManager, type WorldAssetManifestEntry } from "./worldAssetManager";
import { coverWorldStage, fitWorldStage, placeWorldCharacter, worldStageSize } from "./worldStageGeometry";
import type { WorldPresentationPrepareRequest, WorldPresentationRenderer } from "./worldPresentationRenderer";

export const worldStageLayerNames = [
  "BackgroundLayer",
  "CharacterLayer",
  "CgLayer",
  "AtmosphereLayer",
  "TransitionLayer",
] as const;

type StageLayerName = typeof worldStageLayerNames[number];
type ActiveDisplay = { display: Container; assetId: string | null };
type ActiveAnimation = { finish: () => void };

type PixiWorldPresentationRendererOptions = {
  onContextLoss: () => void;
  reducedMotion?: boolean;
  motionIntensity?: "reduced" | "standard" | "cinematic";
  assets?: WorldAssetManager<Texture>;
};

/** PixiJS implementation of the presentation renderer boundary. */
export class PixiWorldPresentationRenderer implements WorldPresentationRenderer {
  readonly kind = "pixi" as const;
  readonly #onContextLoss: () => void;
  readonly #reducedMotion: boolean;
  readonly #motionScale: number;
  readonly #assets: WorldAssetManager<Texture>;
  readonly #ownsAssets: boolean;
  readonly #manifest = new Map<string, WorldAssetManifestEntry>();
  readonly #layers = new Map<StageLayerName, Container>();
  readonly #characters = new Map<string, ActiveDisplay>();
  readonly #animations = new Set<ActiveAnimation>();
  #app: Application | null = null;
  #host: HTMLElement | null = null;
  #stageRoot: Container | null = null;
  #cameraRoot: Container | null = null;
  #background: ActiveDisplay | null = null;
  #cg: ActiveDisplay | null = null;
  #curtain: Graphics | null = null;
  #resizeObserver: ResizeObserver | null = null;
  #contextLossHandler: ((event: Event) => void) | null = null;
  #disposed = false;

  constructor(options: PixiWorldPresentationRendererOptions) {
    this.#onContextLoss = options.onContextLoss;
    this.#reducedMotion = options.reducedMotion
      ?? globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches
      ?? false;
    this.#motionScale = options.motionIntensity === "cinematic" ? 1.25 : 1;
    this.#assets = options.assets ?? createPixiWorldAssetManager();
    this.#ownsAssets = !options.assets;
  }

  async initialize(host: HTMLElement): Promise<void> {
    this.#assertActive();
    if (this.#app) throw new Error("Pixi world renderer is already initialized");
    this.#host = host;
    const app = new Application();
    await app.init({
      resizeTo: host,
      preference: "webgl",
      antialias: true,
      autoDensity: true,
      resolution: Math.min(globalThis.devicePixelRatio || 1, 2),
      backgroundColor: 0x151816,
      backgroundAlpha: 1,
      powerPreference: "high-performance",
    });
    this.#app = app;
    app.canvas.style.width = "100%";
    app.canvas.style.height = "100%";
    app.canvas.style.display = "block";
    host.replaceChildren(app.canvas);

    const stageRoot = new Container({ label: "WorldLogicalStage" });
    const cameraRoot = new Container({ label: "WorldCamera" });
    cameraRoot.pivot.set(worldStageSize.width / 2, worldStageSize.height / 2);
    cameraRoot.position.set(worldStageSize.width / 2, worldStageSize.height / 2);
    stageRoot.addChild(cameraRoot);
    this.#stageRoot = stageRoot;
    this.#cameraRoot = cameraRoot;
    for (const name of worldStageLayerNames) {
      const layer = new Container({ label: name });
      this.#layers.set(name, layer);
      if (name === "TransitionLayer") stageRoot.addChild(layer);
      else cameraRoot.addChild(layer);
    }
    app.stage.addChild(stageRoot);
    this.#installDefaultBackground();
    this.#resize();
    this.#resizeObserver = new ResizeObserver(() => this.#resize());
    this.#resizeObserver.observe(host);
    this.#contextLossHandler = (event) => {
      event.preventDefault();
      this.#onContextLoss();
    };
    app.canvas.addEventListener("webglcontextlost", this.#contextLossHandler);
  }

  async prepare(request: WorldPresentationPrepareRequest, signal?: AbortSignal, onProgress?: (loaded: number, total: number) => void): Promise<void> {
    this.#assertReady();
    this.#assets.registerManifest(request.manifest);
    request.manifest.forEach((entry) => this.#manifest.set(entry.id, entry));
    let loaded = 0;
    onProgress?.(loaded, request.manifest.length);
    await Promise.all(request.manifest.map(async (entry) => {
      try {
        await this.#assets.preload([entry.id], { signal });
      } catch {
        // Each cue owns its documented visual fallback; one bad asset cannot block the plan.
      } finally {
        loaded += 1;
        onProgress?.(loaded, request.manifest.length);
      }
    }));
    if (request.initialAssetId) await this.#showBackground(request.initialAssetId, signal, 0);
  }

  async render(cue: PresentationCue, signal?: AbortSignal): Promise<void> {
    await this.#renderCue(cue, signal, false);
  }

  async recover(cues: readonly PresentationCue[], signal?: AbortSignal): Promise<void> {
    for (const cue of cues) await this.#renderCue(cue, signal, true);
  }

  async #renderCue(cue: PresentationCue, signal: AbortSignal | undefined, recovering: boolean): Promise<void> {
    this.#assertReady();
    if (cue.kind === "background") {
      const assetId = stringCueValue(cue.payload, "assetId", "asset", "id");
      if (assetId) {
        const duration = recovering ? 0 : this.#duration(cue.payload, 320);
        if (stringCueValue(cue.payload, "transition", "transitionKind", "transition_kind") === "curtain") {
          await this.#showCurtain(true, signal, duration / 2);
          await this.#showBackground(assetId, signal, 0);
          await this.#showCurtain(false, signal, duration / 2);
        } else {
          await this.#showBackground(assetId, signal, duration);
        }
      }
      return;
    }
    if (cue.kind === "sprites") {
      await this.#showCharacters(cuePayloadItems(cue, "items"), signal, recovering ? 0 : this.#scaledDuration(220));
      return;
    }
    if (cue.kind === "cg") {
      const task = cuePayloadItems(cue, "tasks").at(-1) ?? cue.payload;
      const assetId = stringCueValue(task, "assetId", "asset", "id");
      if (assetId) await this.#showCg(assetId, signal, recovering ? 0 : this.#duration(task, 320));
      return;
    }
    if (cue.kind === "camera") {
      await this.#moveCamera(cuePayloadItems(cue, "items"), signal, recovering);
    }
  }

  pause(): void {
    this.#app?.ticker.stop();
  }

  resume(): void {
    if (!this.#disposed) this.#app?.ticker.start();
  }

  skip(): void {
    [...this.#animations].forEach((animation) => animation.finish());
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    this.skip();
    this.#resizeObserver?.disconnect();
    this.#resizeObserver = null;
    if (this.#app && this.#contextLossHandler) {
      this.#app.canvas.removeEventListener("webglcontextlost", this.#contextLossHandler);
    }
    this.#contextLossHandler = null;
    this.#releaseDisplay(this.#background);
    this.#releaseDisplay(this.#cg);
    this.#characters.forEach((display) => this.#releaseDisplay(display));
    this.#characters.clear();
    this.#background = null;
    this.#cg = null;
    this.#curtain = null;
    if (this.#ownsAssets) this.#assets.dispose();
    this.#app?.destroy({ removeView: true }, { children: true, texture: false, textureSource: false, context: true });
    this.#app = null;
    this.#host = null;
    this.#stageRoot = null;
    this.#cameraRoot = null;
    this.#layers.clear();
  }

  #installDefaultBackground(): void {
    const layer = this.#layer("BackgroundLayer");
    const background = new Graphics({ label: "DefaultWorldBackground" })
      .rect(0, 0, worldStageSize.width, worldStageSize.height)
      .fill(0x151816);
    layer.addChild(background);
    this.#background = { display: background, assetId: null };
  }

  async #showBackground(assetId: string, signal: AbortSignal | undefined, durationMs: number): Promise<void> {
    let texture: Texture;
    try {
      texture = await this.#assets.acquire(assetId, { signal });
    } catch {
      return;
    }
    const sprite = this.#coverSprite(texture, `Background:${assetId}`);
    const previous = this.#background;
    this.#layer("BackgroundLayer").addChild(sprite);
    sprite.alpha = durationMs > 0 && previous ? 0 : 1;
    this.#background = { display: sprite, assetId };
    await this.#animate(durationMs, (progress) => { sprite.alpha = progress; }, signal);
    if (previous) {
      previous.display.removeFromParent();
      this.#releaseDisplay(previous);
    }
  }

  async #showCg(assetId: string, signal: AbortSignal | undefined, durationMs: number): Promise<void> {
    let texture: Texture;
    try {
      texture = await this.#assets.acquire(assetId, { signal });
    } catch {
      return; // Failed CG retains the current stage and current CG.
    }
    const sprite = this.#coverSprite(texture, `Cg:${assetId}`);
    const previous = this.#cg;
    this.#layer("CgLayer").addChild(sprite);
    sprite.alpha = durationMs > 0 ? 0 : 1;
    this.#cg = { display: sprite, assetId };
    await this.#animate(durationMs, (progress) => { sprite.alpha = progress; }, signal);
    if (previous) {
      previous.display.removeFromParent();
      this.#releaseDisplay(previous);
    }
  }

  async #showCharacters(items: Record<string, unknown>[], signal: AbortSignal | undefined, durationMs: number): Promise<void> {
    const activeActors = new Set<string>();
    await Promise.all(items.map(async (item, index) => {
      const actorId = stringCueValue(item, "actorId", "actor_id", "id") ?? `actor-${index}`;
      activeActors.add(actorId);
      const requestedId = stringCueValue(item, "assetId", "asset", "moodAssetId", "mood_asset_id");
      const avatarId = stringCueValue(item, "avatarAssetId", "avatar_asset_id");
      const fallbackIds = requestedId ? this.#manifest.get(requestedId)?.fallbackIds ?? [] : [];
      const candidates = [requestedId, avatarId, ...fallbackIds].filter((value): value is string => Boolean(value));
      let active: ActiveDisplay | null = null;
      for (const assetId of candidates) {
        try {
          const texture = await this.#assets.acquire(assetId, { signal });
          const sprite = new Sprite({ texture, anchor: { x: 0.5, y: 1 }, label: `Character:${actorId}` });
          const placement = placeWorldCharacter(normalizedCharacterPosition(item.position ?? item.normalizedX, index, items.length), texture.height);
          sprite.position.set(placement.x, placement.y);
          sprite.scale.set(placement.scale);
          active = { display: sprite, assetId };
          break;
        } catch {
          // Continue through mood -> avatar -> silhouette.
        }
      }
      if (!active) {
        const silhouette = new Graphics({ label: `CharacterSilhouette:${actorId}` })
          .circle(0, -650, 130)
          .roundRect(-190, -540, 380, 540, 170)
          .fill({ color: 0x0b0d0c, alpha: 0.82 });
        const placement = placeWorldCharacter(normalizedCharacterPosition(item.position ?? item.normalizedX, index, items.length), 800);
        silhouette.position.set(placement.x, placement.y);
        active = { display: silhouette, assetId: null };
      }
      const previous = this.#characters.get(actorId);
      this.#layer("CharacterLayer").addChild(active.display);
      active.display.alpha = durationMs > 0 && !this.#reducedMotion ? 0 : 1;
      this.#characters.set(actorId, active);
      await this.#animate(durationMs, (progress) => { active!.display.alpha = progress; }, signal);
      if (previous) {
        previous.display.removeFromParent();
        this.#releaseDisplay(previous);
      }
    }));
    for (const [actorId, display] of this.#characters) {
      if (activeActors.has(actorId)) continue;
      display.display.removeFromParent();
      this.#releaseDisplay(display);
      this.#characters.delete(actorId);
    }
  }

  async #showCurtain(visible: boolean, signal: AbortSignal | undefined, durationMs: number): Promise<void> {
    if (!this.#curtain) {
      this.#curtain = new Graphics({ label: "WorldCurtain" })
        .rect(0, 0, worldStageSize.width, worldStageSize.height)
        .fill(0x080908);
      this.#curtain.alpha = 0;
      this.#layer("TransitionLayer").addChild(this.#curtain);
    }
    const curtain = this.#curtain;
    const start = curtain.alpha;
    const target = visible ? 1 : 0;
    await this.#animate(durationMs, (progress) => {
      curtain.alpha = start + (target - start) * progress;
    }, signal);
  }

  async #moveCamera(items: Record<string, unknown>[], signal?: AbortSignal, recovering = false): Promise<void> {
    const camera = this.#cameraRoot;
    if (!camera || this.#reducedMotion) return;
    for (const item of items) {
      const startX = camera.position.x;
      const startY = camera.position.y;
      const startScale = camera.scale.x;
      const targetX = worldStageSize.width / 2 + (numericCueValue(item, "x", "offsetX", "offset_x") ?? 0);
      const targetY = worldStageSize.height / 2 + (numericCueValue(item, "y", "offsetY", "offset_y") ?? 0);
      const targetScale = Math.max(0.8, Math.min(1.4, numericCueValue(item, "zoom", "scale") ?? startScale));
      await this.#animate(recovering ? 0 : this.#duration(item, 400), (progress) => {
        camera.position.set(
          startX + (targetX - startX) * progress,
          startY + (targetY - startY) * progress,
        );
        camera.scale.set(startScale + (targetScale - startScale) * progress);
      }, signal);
    }
  }

  #coverSprite(texture: Texture, label: string): Sprite {
    const fit = coverWorldStage(texture.width, texture.height);
    const sprite = new Sprite({ texture, label });
    sprite.position.set(fit.x, fit.y);
    sprite.scale.set(fit.scale);
    return sprite;
  }

  async #animate(durationMs: number, update: (progress: number) => void, signal?: AbortSignal): Promise<void> {
    const app = this.#app;
    if (!app || this.#reducedMotion || durationMs <= 0) {
      update(1);
      return;
    }
    await new Promise<void>((resolve, reject) => {
      let elapsed = 0;
      let settled = false;
      const cleanup = () => {
        app.ticker.remove(tick);
        signal?.removeEventListener("abort", abort);
        this.#animations.delete(animation);
      };
      const finish = () => {
        if (settled) return;
        settled = true;
        update(1);
        cleanup();
        resolve();
      };
      const abort = () => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(signal?.reason ?? new DOMException("Aborted", "AbortError"));
      };
      const tick = (ticker: Ticker) => {
        elapsed += ticker.elapsedMS;
        const progress = Math.min(1, elapsed / durationMs);
        update(progress);
        if (progress === 1) finish();
      };
      const animation = { finish };
      this.#animations.add(animation);
      signal?.addEventListener("abort", abort, { once: true });
      app.ticker.add(tick);
    });
  }

  #duration(payload: Record<string, unknown>, fallback: number): number {
    if (this.#reducedMotion) return 0;
    return this.#scaledDuration(numericCueValue(payload, "durationMs", "duration_ms") ?? fallback);
  }

  #scaledDuration(durationMs: number): number {
    return Math.max(0, durationMs * this.#motionScale);
  }

  #resize(): void {
    const host = this.#host;
    const stage = this.#stageRoot;
    if (!host || !stage) return;
    const fit = fitWorldStage(Math.max(1, host.clientWidth), Math.max(1, host.clientHeight));
    stage.position.set(fit.offsetX, fit.offsetY);
    stage.scale.set(fit.scale);
  }

  #releaseDisplay(active: ActiveDisplay | null): void {
    if (!active) return;
    active.display.destroy({ children: true, texture: false, textureSource: false });
    if (active.assetId) this.#assets.release(active.assetId);
  }

  #layer(name: StageLayerName): Container {
    const layer = this.#layers.get(name);
    if (!layer) throw new Error(`Pixi world stage layer ${name} is unavailable`);
    return layer;
  }

  #assertReady(): void {
    this.#assertActive();
    if (!this.#app) throw new Error("Pixi world renderer is not initialized");
  }

  #assertActive(): void {
    if (this.#disposed) throw new Error("Pixi world renderer is disposed");
  }
}

/** Creates the texture cache retained by the World route runtime. */
export function createPixiWorldAssetManager() {
  return new WorldAssetManager<Texture>({
    loader: loadPixiWorldTexture,
    destroy: (texture) => texture.destroy(true),
    softBudgetBytes: 256 * 1024 * 1024,
    maxEntries: 64,
    timeoutMs: 10_000,
  });
}

/** Creates the graphical adapter without exposing PixiJS to React callers. */
export function createPixiWorldPresentationRenderer(options: PixiWorldPresentationRendererOptions) {
  return new PixiWorldPresentationRenderer(options);
}
