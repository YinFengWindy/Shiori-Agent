import type { BrowserWindow } from "electron";
import { desktopPetViewport, clampDesktopPetPosition } from "./geometry.js";
import { desktopPetPositionFromCursor } from "./drag.js";
import { bindDesktopPetSettings } from "./settings.js";
import type { DesktopPetBinding, DesktopPetPosition, DesktopPetSettings, DesktopPetState } from "./types.js";

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
};

/** Serializes desktop-pet lifecycle operations so a stale enable cannot recreate a disabled pet. */
export class DesktopPetController {
  private readonly createWindow: DesktopPetControllerOptions["createWindow"];
  private readonly displayForWindow: DesktopPetControllerOptions["displayForWindow"];
  private window: BrowserWindow | null = null;
  private queue = Promise.resolve();
  private activeRoleId = "";
  private dragPointerOffset: DesktopPetPosition | null = null;
  private dragFollowTimer: ReturnType<typeof setInterval> | null = null;

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

  /** Starts following the system cursor while preserving the initial pointer offset. */
  beginDrag(pointerOffsetX: number, pointerOffsetY: number, pointerScreenX?: number, pointerScreenY?: number): void {
    if (!this.isRunning || !Number.isFinite(pointerOffsetX) || !Number.isFinite(pointerOffsetY)) return;
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

  /** Stops following the system cursor and persists only the final drag location. */
  endDrag(): void {
    if (!this.dragPointerOffset || !this.window) return;
    this.followDrag();
    this.stopDragFollow();
    this.dragPointerOffset = null;
    this.persistPosition(this.activeRoleId, this.window);
  }

  private enqueue(operation: () => Promise<void>): Promise<void> {
    const next = this.queue.then(operation, operation);
    this.queue = next.catch(() => undefined);
    return next;
  }

  private async load(binding: DesktopPetBinding, settings: DesktopPetSettings, state: DesktopPetState): Promise<void> {
    const created = this.window === null;
    const window = this.window ?? this.createWindow({ openLocalAttachment: this.options.openLocalAttachment });
    const display = this.displayForWindow(window);
    const key = `${binding.roleId}:${display.id}`;
    const fallback = {
      x: display.workArea.x + display.workArea.width - desktopPetViewport.width,
      y: display.workArea.y + display.workArea.height - desktopPetViewport.height,
    };
    const position = clampDesktopPetPosition(settings.positions[key] ?? fallback, display.workArea);
    window.setPosition(position.x, position.y);
    this.activeRoleId = binding.roleId;
    const sendLoad = () => {
      window.showInactive();
      window.webContents.send("desktop:pet-load", { package: binding.package, state });
    };
    if (created) {
      window.once("ready-to-show", sendLoad);
      window.on("closed", () => {
        if (this.window !== window) return;
        this.stopDragFollow();
        this.dragPointerOffset = null;
        this.window = null;
      });
    } else {
      sendLoad();
    }
    this.window = window;
  }

  private followDrag(): void {
    if (!this.dragPointerOffset) return;
    this.moveDrag(this.options.cursorScreenPoint());
  }

  private moveTo(position: DesktopPetPosition): void {
    const window = this.window;
    if (!window || window.isDestroyed()) return;
    const display = this.displayForWindow(window);
    const clamped = clampDesktopPetPosition(position, display.workArea);
    window.setPosition(clamped.x, clamped.y);
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

  private destroyWindow(): void {
    this.stopDragFollow();
    this.dragPointerOffset = null;
    this.window?.destroy();
    this.window = null;
  }
}
