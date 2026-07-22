import type { BrowserWindow } from "electron";
import { desktopPetViewport, clampDesktopPetPosition } from "./geometry.js";
import { desktopPetPositionFromCursor, type DesktopPetPoint } from "./drag.js";
import { bindDesktopPetSettings } from "./settings.js";
import type { DesktopPetBinding, DesktopPetSettings, DesktopPetState } from "./types.js";

type DesktopPetControllerOptions = {
  getSettings: () => DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: (roleId?: string) => Promise<DesktopPetBinding | null>;
  createWindow: (options: { openLocalAttachment: (url: string) => Promise<unknown> | unknown }) => BrowserWindow;
  displayForWindow: (window: BrowserWindow | null) => { id: string | number; workArea: { x: number; y: number; width: number; height: number } };
  getCursorPosition: () => DesktopPetPoint;
  openLocalAttachment: (url: string) => Promise<unknown> | unknown;
};

const desktopPetDragIntervalMilliseconds = 1000 / 60;

/** Serializes desktop-pet lifecycle operations so a stale enable cannot recreate a disabled pet. */
export class DesktopPetController {
  private readonly createWindow: DesktopPetControllerOptions["createWindow"];
  private readonly displayForWindow: DesktopPetControllerOptions["displayForWindow"];
  private window: BrowserWindow | null = null;
  private queue = Promise.resolve();
  private activeRoleId = "";
  private dragPointerOffset: DesktopPetPoint | null = null;
  private lastDragPosition: DesktopPetPoint | null = null;
  private dragTimer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly options: DesktopPetControllerOptions) {
    this.createWindow = options.createWindow;
    this.displayForWindow = options.displayForWindow;
  }

  get isRunning(): boolean {
    return Boolean(this.window && !this.window.isDestroyed());
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

  /** Starts tracking the system cursor from the renderer's pointer-down command. */
  beginDrag(pointerOffsetX: number, pointerOffsetY: number): void {
    if (!this.window || !Number.isFinite(pointerOffsetX) || !Number.isFinite(pointerOffsetY)) return;
    this.dragPointerOffset = { x: pointerOffsetX, y: pointerOffsetY };
    this.lastDragPosition = null;
    this.followCursor();
    this.stopDragTracking();
    this.dragTimer = setInterval(() => this.followCursor(), desktopPetDragIntervalMilliseconds);
  }

  /** Stops cursor tracking and persists the final desktop-pet position. */
  endDrag(): void {
    if (!this.dragPointerOffset) return;
    this.followCursor();
    this.dragPointerOffset = null;
    this.stopDragTracking();
    if (this.window) this.persistPosition(this.activeRoleId, this.window);
  }

  /** Moves at a stable cadence without putting renderer pointermove events on IPC. */
  private followCursor(): void {
    if (!this.dragPointerOffset) return;
    this.moveTo(desktopPetPositionFromCursor(this.options.getCursorPosition(), this.dragPointerOffset));
  }

  private stopDragTracking(): void {
    if (this.dragTimer) clearInterval(this.dragTimer);
    this.dragTimer = null;
  }

  private moveTo(position: DesktopPetPoint): void {
    if (!this.window) return;
    const display = this.displayForWindow(this.window);
    const clampedPosition = clampDesktopPetPosition(position, display.workArea);
    this.lastDragPosition = clampedPosition;
    this.window.setPosition(clampedPosition.x, clampedPosition.y, false);
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
      window.on("moved", () => {
        const [x, y] = window.getPosition();
        if (this.lastDragPosition?.x === x && this.lastDragPosition.y === y) return;
        this.persistPosition(this.activeRoleId, window);
      });
      window.on("closed", () => {
        if (this.window === window) this.window = null;
      });
    } else {
      sendLoad();
    }
    this.window = window;
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

  private destroyWindow(): void {
    this.dragPointerOffset = null;
    this.lastDragPosition = null;
    this.stopDragTracking();
    this.window?.destroy();
    this.window = null;
  }
}
