import type { BrowserWindow } from "electron";
import { desktopPetViewport, clampDesktopPetPosition } from "./geometry.js";
import { desktopPetPositionFromCursor } from "./drag.js";
import {
  advanceDesktopPetMomentum,
  desktopPetMomentumIntervalMs,
  shouldStopDesktopPetMomentum,
  type DesktopPetMomentum,
} from "./momentum.js";
import { bindDesktopPetSettings } from "./settings.js";
import type { DesktopPetBinding, DesktopPetPosition, DesktopPetSettings, DesktopPetState } from "./types.js";
import type { PetObservationPayload } from "../observation/types.js";

/** Keeps the main-process cursor follower aligned with the display refresh rate. */
export const desktopPetDragFollowIntervalMs = 1000 / 60;

type DesktopPetControllerOptions = {
  getSettings: () => DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: (roleId?: string) => Promise<DesktopPetBinding | null>;
  createWindow: (options: { openLocalAttachment: (url: string) => Promise<unknown> | unknown }) => BrowserWindow;
  displayForWindow: (window: BrowserWindow | null) => { id: string | number; workArea: { x: number; y: number; width: number; height: number } };
  cursorScreenPoint: () => DesktopPetPosition;
  openLocalAttachment: (url: string) => Promise<unknown> | unknown;
  onUnavailable?: () => void;
};

/** Serializes desktop-pet lifecycle operations so a stale enable cannot recreate a disabled pet. */
export class DesktopPetController {
  private readonly createWindow: DesktopPetControllerOptions["createWindow"];
  private readonly displayForWindow: DesktopPetControllerOptions["displayForWindow"];
  private window: BrowserWindow | null = null;
  private queue = Promise.resolve();
  private activeRoleId = "";
  private activePackageId = "";
  private activeLoad: { binding: DesktopPetBinding; state: DesktopPetState } | null = null;
  private rendererIsReady = false;
  private windowIsReadyToShow = false;
  private latestObservation: PetObservationPayload | null = null;
  private dragPointerOffset: DesktopPetPosition | null = null;
  private dragFollowTimer: ReturnType<typeof setInterval> | null = null;
  private momentum: DesktopPetMomentum | null = null;
  private momentumStartedAtMs = 0;
  private momentumUpdatedAtMs = 0;
  private momentumTimer: ReturnType<typeof setTimeout> | null = null;

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
    if (this.windowIsReadyToShow) window?.showInactive();
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

  /** Publishes observation state without exposing frames or model output internals. */
  publishObservation(payload: PetObservationPayload): void {
    this.latestObservation = payload;
    if (this.rendererIsReady) this.window?.webContents.send("desktop:pet-observation", payload);
  }

  /** Starts following the system cursor while preserving the initial pointer offset. */
  beginDrag(pointerOffsetX: number, pointerOffsetY: number, pointerScreenX?: number, pointerScreenY?: number): void {
    if (!this.isRunning || !Number.isFinite(pointerOffsetX) || !Number.isFinite(pointerOffsetY)) return;
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
    if (
      this.activeRoleId
      && (this.activeRoleId !== binding.roleId || this.activePackageId !== binding.package.id)
    ) this.options.onUnavailable?.();
    const created = this.window === null;
    const window = this.window ?? this.createWindow({ openLocalAttachment: this.options.openLocalAttachment });
    if (created) {
      this.rendererIsReady = false;
      this.windowIsReadyToShow = false;
    }
    const display = this.displayForWindow(window);
    const key = `${binding.roleId}:${display.id}`;
    const fallback = {
      x: display.workArea.x + display.workArea.width - desktopPetViewport.width,
      y: display.workArea.y + display.workArea.height - desktopPetViewport.height,
    };
    const position = clampDesktopPetPosition(settings.positions[key] ?? fallback, display.workArea);
    window.setPosition(position.x, position.y);
    this.activeRoleId = binding.roleId;
    this.activePackageId = binding.package.id;
    this.activeLoad = { binding, state };
    if (created) {
      window.once("ready-to-show", () => {
        this.windowIsReadyToShow = true;
        if (this.rendererIsReady) window.showInactive();
      });
      window.on("closed", () => {
        if (this.window !== window) return;
        this.stopDragFollow();
        this.dragPointerOffset = null;
        this.window = null;
        this.activeRoleId = "";
        this.activePackageId = "";
        this.activeLoad = null;
        this.rendererIsReady = false;
        this.windowIsReadyToShow = false;
        this.options.onUnavailable?.();
      });
    }
    this.window = window;
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
    window.setPosition(rounded.x, rounded.y);
    return rounded;
  }

  /** Starts the same decaying release glide used by the Codex desktop-pet overlay. */
  private startMomentum(velocity: DesktopPetPosition): void {
    const window = this.window;
    if (!window || window.isDestroyed()) return;
    this.stopMomentum();
    const [x, y] = window.getPosition();
    this.momentum = { position: { x, y }, velocity };
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
    const [x, y] = window.getPosition();
    const settings = this.options.getSettings();
    void this.options.saveSettings({
      ...settings,
      positions: { ...settings.positions, [`${roleId}:${display.id}`]: clampDesktopPetPosition({ x, y }, display.workArea) },
    });
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

  private destroyWindow(): void {
    if (this.window) this.options.onUnavailable?.();
    this.stopDragFollow();
    this.stopMomentum();
    this.dragPointerOffset = null;
    this.window?.destroy();
    this.window = null;
    this.activeRoleId = "";
    this.activePackageId = "";
    this.activeLoad = null;
    this.rendererIsReady = false;
    this.windowIsReadyToShow = false;
  }
}
