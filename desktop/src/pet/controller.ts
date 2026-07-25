import type { BrowserWindow } from "electron";
import {
  clampDesktopPetPosition,
  desktopPetViewport,
} from "./geometry.js";
import { DesktopPetBubbleLayout } from "./bubbleLayout.js";
import { desktopPetPositionFromCursor } from "./drag.js";
import {
  advanceDesktopPetMomentum,
  desktopPetMomentumIntervalMs,
  shouldStopDesktopPetMomentum,
  type DesktopPetMomentum,
} from "./momentum.js";
import { bindDesktopPetSettings } from "./settings.js";
import type {
  DesktopPetBinding,
  DesktopPetActionPayload,
  DesktopPetPosition,
  DesktopPetSettings,
  DesktopPetState,
  DesktopPetWorkArea,
} from "./types.js";
import type { PetObservationPayload } from "../observation/types.js";

/** Keeps the main-process cursor follower aligned with the display refresh rate. */
export const desktopPetDragFollowIntervalMs = 1000 / 60;
/** Keeps role-requested moves visible as a short, deliberate desktop animation. */
export const desktopPetAgentMoveDurationMs = 900;
const desktopPetAgentMoveFrameMs = 16;

type DesktopPetControllerOptions = {
  getSettings: () => DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: (roleId?: string) => Promise<DesktopPetBinding | null>;
  createWindow: (options: { openLocalAttachment: (url: string) => Promise<unknown> | unknown }) => BrowserWindow;
  displayForWindow: (window: BrowserWindow | null) => { id: string | number; workArea: DesktopPetWorkArea };
  cursorScreenPoint: () => DesktopPetPosition;
  openLocalAttachment: (url: string) => Promise<unknown> | unknown;
};

/** Serializes desktop-pet lifecycle operations so a stale enable cannot recreate a disabled pet. */
export class DesktopPetController {
  private readonly createWindow: DesktopPetControllerOptions["createWindow"];
  private readonly displayForWindow: DesktopPetControllerOptions["displayForWindow"];
  private window: BrowserWindow | null = null;
  private queue = Promise.resolve();
  private activeRoleId = "";
  private activeLoad: { binding: DesktopPetBinding; state: DesktopPetState } | null = null;
  private rendererIsReady = false;
  private latestObservation: PetObservationPayload | null = null;
  private readonly bubbleLayout = new DesktopPetBubbleLayout();
  private anchorPosition: DesktopPetPosition | null = null;
  private dragPointerOffset: DesktopPetPosition | null = null;
  private dragFollowTimer: ReturnType<typeof setInterval> | null = null;
  private momentum: DesktopPetMomentum | null = null;
  private momentumStartedAtMs = 0;
  private momentumUpdatedAtMs = 0;
  private momentumTimer: ReturnType<typeof setTimeout> | null = null;
  private agentMoveTimer: ReturnType<typeof setTimeout> | null = null;
  private agentMoveAnimation: {
    window: BrowserWindow;
    roleId: string;
    from: DesktopPetPosition;
    to: DesktopPetPosition;
    startedAtMs: number;
  } | null = null;

  constructor(private readonly options: DesktopPetControllerOptions) {
    this.createWindow = options.createWindow;
    this.displayForWindow = options.displayForWindow;
  }

  get isRunning(): boolean {
    return Boolean(this.window && !this.window.isDestroyed());
  }

  /** Returns whether an IPC sender owns the currently active pet window. */
  isPetWindow(window: BrowserWindow | null): boolean {
    return Boolean(window && window === this.window && !window.isDestroyed());
  }

  /** Replays the current package only after the pet renderer has installed its IPC listeners. */
  rendererReady(window: BrowserWindow | null): boolean {
    if (!this.isPetWindow(window)) return false;
    this.rendererIsReady = true;
    this.sendCurrentLoad(window as BrowserWindow);
    window?.showInactive();
    return true;
  }

  show(): Promise<void> {
    return this.enqueue(async () => {
      const binding = await this.options.resolveBinding();
      if (!binding) throw new Error("没有已启用且已选择素材的桌宠角色");
      const nextSettings = bindDesktopPetSettings(this.options.getSettings(), binding, true);
      await this.load(binding, nextSettings, "idle");
      await this.options.saveSettings(nextSettings);
    });
  }

  hide(): Promise<void> {
    return this.enqueue(async () => {
      this.destroyWindow();
      await this.options.saveSettings({ ...this.options.getSettings(), visible: false });
    });
  }

  sync(forceVisible?: boolean): Promise<void> {
    return this.enqueue(async () => {
      const binding = await this.options.resolveBinding();
      if (!binding) {
        this.destroyWindow();
        await this.options.saveSettings({ ...this.options.getSettings(), visible: false, roleId: null, packageId: null });
        return;
      }
      const current = this.options.getSettings();
      const changedBinding = current.roleId !== binding.roleId || current.packageId !== binding.package.id;
      const nextSettings = bindDesktopPetSettings(
        current,
        binding,
        forceVisible ?? (changedBinding || current.visible),
      );
      if (nextSettings.visible) await this.load(binding, nextSettings, "idle");
      else this.destroyWindow();
      await this.options.saveSettings(nextSettings);
    });
  }

  restore(): Promise<void> {
    return this.sync();
  }

  play(state: DesktopPetState): void {
    this.window?.webContents.send("desktop:pet-play", { state });
  }

  /** Executes one already-authorized role action without exposing window APIs to the renderer. */
  handleAgentAction(value: unknown): void {
    if (!isDesktopPetActionPayload(value)) return;
    if (!this.isRunning || value.role_id !== this.activeRoleId || value.channel !== "desktop") return;
    if (value.kind === "play") {
      const state = value.name ? this.activeLoad?.binding.actions?.[value.name] : undefined;
      if (state) this.playTransient(state);
      return;
    }
    if (!value.target) return;
    const display = this.displayForWindow(this.window);
    const current = this.currentAnchorPosition(this.window as BrowserWindow);
    const next = desktopPetTargetPosition(value.target, display.workArea);
    this.stopMomentum();
    this.animateAgentMove(next);
    if (value.animation === "run") {
      const state = next.x < current.x ? "running-left" : next.x > current.x ? "running-right" : "idle";
      this.playTransient(state);
    }
  }

  /** Publishes observation state without exposing frames or model output internals. */
  publishObservation(payload: PetObservationPayload): void {
    this.latestObservation = payload;
    if (this.rendererIsReady) this.window?.webContents.send("desktop:pet-observation", payload);
  }

  /** Resizes the transparent window around the renderer-measured full reply bubble. */
  setBubbleHeight(height: number): void {
    if (!this.bubbleLayout.setMeasuredHeight(height)) return;
    const position = this.anchorPosition;
    if (position) this.moveTo(position);
  }

  /** Starts following the system cursor while preserving the initial pointer offset. */
  beginDrag(pointerOffsetX: number, pointerOffsetY: number, pointerScreenX?: number, pointerScreenY?: number): void {
    if (!this.isRunning || !Number.isFinite(pointerOffsetX) || !Number.isFinite(pointerOffsetY)) return;
    this.stopAgentMoveAnimation();
    this.stopMomentum();
    this.stopDragFollow();
    this.dragPointerOffset = { x: pointerOffsetX, y: pointerOffsetY };
    if (
      typeof pointerScreenX === "number"
      && typeof pointerScreenY === "number"
      && Number.isFinite(pointerScreenX)
      && Number.isFinite(pointerScreenY)
    ) {
      this.moveDrag({ x: pointerScreenX, y: pointerScreenY });
    } else {
      this.followDrag();
    }
    this.dragFollowTimer = setInterval(() => this.followDrag(), desktopPetDragFollowIntervalMs);
  }

  /** Applies an immediate renderer cursor sample before the next fallback poll. */
  moveDrag(cursor: DesktopPetPosition): void {
    if (!this.dragPointerOffset) return;
    this.moveTo(desktopPetPositionFromCursor(cursor, this.dragPointerOffset));
  }

  /** Stops following the cursor and either persists or glides with the Codex release velocity. */
  endDrag(releaseCursor?: DesktopPetPosition, releaseVelocity?: DesktopPetPosition): void {
    if (!this.dragPointerOffset || !this.window) return;
    if (releaseCursor) this.moveDrag(releaseCursor);
    else this.followDrag();
    this.stopDragFollow();
    this.dragPointerOffset = null;
    if (releaseVelocity && Number.isFinite(releaseVelocity.x) && Number.isFinite(releaseVelocity.y)) {
      this.startMomentum(releaseVelocity);
      return;
    }
    this.persistPosition(this.activeRoleId, this.window);
  }

  private enqueue(operation: () => Promise<void>): Promise<void> {
    const next = this.queue.then(operation, operation);
    this.queue = next.catch(() => undefined);
    return next;
  }

  private async load(binding: DesktopPetBinding, settings: DesktopPetSettings, state: DesktopPetState): Promise<void> {
    this.stopAgentMoveAnimation();
    const created = this.window === null;
    const window = this.window ?? this.createWindow({ openLocalAttachment: this.options.openLocalAttachment });
    if (created) this.rendererIsReady = false;
    const display = this.displayForWindow(window);
    const key = `${binding.roleId}:${display.id}`;
    const fallback = {
      x: display.workArea.x + display.workArea.width - desktopPetViewport.width,
      y: display.workArea.y + display.workArea.height - desktopPetViewport.height,
    };
    const position = clampDesktopPetPosition(settings.positions[key] ?? fallback, display.workArea);
    this.activeRoleId = binding.roleId;
    this.activeLoad = { binding, state };
    if (created) {
      window.once("ready-to-show", () => {
        if (this.rendererIsReady) window.showInactive();
      });
      window.on("closed", () => {
        if (this.window !== window) return;
        this.stopAgentMoveAnimation();
        this.stopDragFollow();
        this.dragPointerOffset = null;
        this.window = null;
        this.activeRoleId = "";
        this.activeLoad = null;
        this.rendererIsReady = false;
        this.anchorPosition = null;
        this.bubbleLayout.reset();
      });
    }
    this.window = window;
    this.moveTo(position);
    if (!created && this.rendererIsReady) this.sendCurrentLoad(window);
  }

  private sendCurrentLoad(window: BrowserWindow): void {
    if (window !== this.window || window.isDestroyed() || !this.activeLoad) return;
    window.webContents.send("desktop:pet-load", {
      package: this.activeLoad.binding.package,
      state: this.activeLoad.state,
    });
    if (this.latestObservation) {
      window.webContents.send("desktop:pet-observation", this.latestObservation);
    }
    this.publishBubbleLayout(window);
  }

  private followDrag(): void {
    if (!this.dragPointerOffset) return;
    this.moveDrag(this.options.cursorScreenPoint());
  }

  private moveTo(position: DesktopPetPosition): DesktopPetPosition | null {
    const window = this.window;
    if (!window || window.isDestroyed()) return null;
    const display = this.displayForWindow(window);
    const clamped = clampDesktopPetPosition(position, display.workArea);
    const rounded = { x: Math.round(clamped.x), y: Math.round(clamped.y) };
    this.anchorPosition = rounded;
    window.setBounds(this.bubbleLayout.place(rounded, display.workArea));
    this.publishBubbleLayout(window);
    return rounded;
  }

  /** Interpolates a role-requested move while keeping the renderer and bounds in one process. */
  private animateAgentMove(position: DesktopPetPosition): void {
    const window = this.window;
    if (!window || window.isDestroyed()) return;
    this.stopAgentMoveAnimation();
    const display = this.displayForWindow(window);
    const from = this.currentAnchorPosition(window);
    const to = clampDesktopPetPosition(position, display.workArea);
    if (from.x === to.x && from.y === to.y) {
      this.moveTo(to);
      this.persistPosition(this.activeRoleId, window);
      return;
    }
    const animation = {
      window,
      roleId: this.activeRoleId,
      from,
      to,
      startedAtMs: Date.now(),
    };
    this.agentMoveAnimation = animation;
    const tick = () => {
      this.agentMoveTimer = null;
      if (
        this.agentMoveAnimation !== animation
        || this.window !== window
        || window.isDestroyed()
      ) {
        return;
      }
      const progress = Math.min(
        1,
        Math.max(0, (Date.now() - animation.startedAtMs) / desktopPetAgentMoveDurationMs),
      );
      const eased = 1 - (1 - progress) ** 3;
      this.moveTo({
        x: animation.from.x + (animation.to.x - animation.from.x) * eased,
        y: animation.from.y + (animation.to.y - animation.from.y) * eased,
      });
      if (progress >= 1) {
        this.agentMoveAnimation = null;
        this.persistPosition(animation.roleId, window);
        return;
      }
      this.agentMoveTimer = setTimeout(tick, desktopPetAgentMoveFrameMs);
    };
    this.agentMoveTimer = setTimeout(tick, desktopPetAgentMoveFrameMs);
  }

  /** Starts the same decaying release glide used by the Codex desktop-pet overlay. */
  private startMomentum(velocity: DesktopPetPosition): void {
    const window = this.window;
    if (!window || window.isDestroyed()) return;
    this.stopMomentum();
    this.momentum = { position: this.currentAnchorPosition(window), velocity };
    this.momentumStartedAtMs = Date.now();
    this.momentumUpdatedAtMs = this.momentumStartedAtMs;
    this.scheduleMomentum();
  }

  private scheduleMomentum(): void {
    this.momentumTimer = setTimeout(() => this.advanceMomentum(), desktopPetMomentumIntervalMs);
  }

  private advanceMomentum(): void {
    this.momentumTimer = null;
    const momentum = this.momentum;
    const window = this.window;
    if (!momentum || !window || window.isDestroyed()) {
      this.stopMomentum();
      return;
    }
    const now = Date.now();
    const next = advanceDesktopPetMomentum(momentum, now - this.momentumUpdatedAtMs);
    this.momentumUpdatedAtMs = now;
    const requestedPosition = next.position;
    const applied = this.moveTo(requestedPosition);
    if (!applied) {
      this.stopMomentum();
      return;
    }
    next.position = applied;
    if (applied.x !== Math.round(requestedPosition.x)) next.velocity.x = 0;
    if (applied.y !== Math.round(requestedPosition.y)) next.velocity.y = 0;
    this.momentum = next;
    if (shouldStopDesktopPetMomentum(next, now - this.momentumStartedAtMs)) {
      this.stopMomentum();
      this.persistPosition(this.activeRoleId, window);
      return;
    }
    this.scheduleMomentum();
  }

  private persistPosition(roleId: string, window: BrowserWindow): void {
    const display = this.displayForWindow(window);
    const position = this.currentAnchorPosition(window);
    const settings = this.options.getSettings();
    void this.options.saveSettings({
      ...settings,
      positions: { ...settings.positions, [`${roleId}:${display.id}`]: clampDesktopPetPosition(position, display.workArea) },
    });
  }

  private currentAnchorPosition(window: BrowserWindow): DesktopPetPosition {
    if (this.anchorPosition) return { ...this.anchorPosition };
    const [x, y] = window.getPosition();
    return this.bubbleLayout.anchorFromWindow({ x, y });
  }

  private publishBubbleLayout(window: BrowserWindow): void {
    if (!this.rendererIsReady || window.isDestroyed()) return;
    window.webContents.send("desktop:pet-bubble-layout", this.bubbleLayout.layout);
  }

  private playTransient(state: DesktopPetState): void {
    this.window?.webContents.send("desktop:pet-play", { state, transient: true });
  }

  private stopDragFollow(): void {
    if (this.dragFollowTimer) clearInterval(this.dragFollowTimer);
    this.dragFollowTimer = null;
  }

  private stopMomentum(): void {
    if (this.momentumTimer) clearTimeout(this.momentumTimer);
    this.momentumTimer = null;
    this.momentum = null;
  }

  private stopAgentMoveAnimation(): void {
    if (this.agentMoveTimer) clearTimeout(this.agentMoveTimer);
    this.agentMoveTimer = null;
    this.agentMoveAnimation = null;
  }

  private destroyWindow(): void {
    this.stopAgentMoveAnimation();
    this.stopDragFollow();
    this.stopMomentum();
    this.dragPointerOffset = null;
    this.window?.destroy();
    this.window = null;
    this.activeRoleId = "";
    this.activeLoad = null;
    this.rendererIsReady = false;
    this.anchorPosition = null;
    this.bubbleLayout.reset();
  }
}

function isDesktopPetActionPayload(value: unknown): value is DesktopPetActionPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as Partial<DesktopPetActionPayload>;
  return payload.channel === "desktop"
    && typeof payload.role_id === "string"
    && (payload.kind === "move" || payload.kind === "play");
}

function desktopPetTargetPosition(
  target: NonNullable<DesktopPetActionPayload["target"]>,
  workArea: DesktopPetWorkArea,
): DesktopPetPosition {
  const right = workArea.x + workArea.width - desktopPetViewport.width;
  const bottom = workArea.y + workArea.height - desktopPetViewport.height;
  if (target === "top_left") return { x: workArea.x, y: workArea.y };
  if (target === "top_right") return { x: right, y: workArea.y };
  if (target === "bottom_left") return { x: workArea.x, y: bottom };
  if (target === "bottom_right") return { x: right, y: bottom };
  return {
    x: workArea.x + (workArea.width - desktopPetViewport.width) / 2,
    y: workArea.y + (workArea.height - desktopPetViewport.height) / 2,
  };
}
