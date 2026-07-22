import type { BrowserWindow } from "electron";
import { desktopPetViewport, clampDesktopPetPosition, createDesktopPetWindow, displayForDesktopPet } from "./window.js";
import { activateDesktopPetSettings } from "./settings.js";
import type { DesktopPetBinding, DesktopPetSettings, DesktopPetState } from "./types.js";

type DesktopPetControllerOptions = {
  getSettings: () => DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: (roleId: string) => Promise<DesktopPetBinding | null>;
  createWindow?: typeof createDesktopPetWindow;
  openLocalAttachment: (url: string) => Promise<unknown> | unknown;
};

/** Serializes desktop-pet lifecycle operations so a stale enable cannot recreate a disabled pet. */
export class DesktopPetController {
  private readonly createWindow: typeof createDesktopPetWindow;
  private window: BrowserWindow | null = null;
  private queue = Promise.resolve();
  private activeRoleId = "";

  constructor(private readonly options: DesktopPetControllerOptions) {
    this.createWindow = options.createWindow ?? createDesktopPetWindow;
  }

  get isRunning(): boolean {
    return Boolean(this.window && !this.window.isDestroyed());
  }

  enable(roleId = this.options.getSettings().roleId): Promise<void> {
    return this.enqueue(async () => {
      if (!roleId) throw new Error("桌宠尚未选择角色");
      const binding = await this.options.resolveBinding(roleId);
      if (!binding) throw new Error("角色尚未选择桌宠素材");
      const nextSettings = activateDesktopPetSettings(this.options.getSettings(), binding);
      await this.load(binding, nextSettings, "idle");
      await this.options.saveSettings(nextSettings);
    });
  }

  disable(): Promise<void> {
    return this.enqueue(async () => {
      this.destroyWindow();
      await this.options.saveSettings({ ...this.options.getSettings(), enabled: false });
    });
  }

  restore(): Promise<void> {
    const settings = this.options.getSettings();
    return settings.enabled ? this.enable() : Promise.resolve();
  }

  play(state: DesktopPetState): void {
    this.window?.webContents.send("desktop:pet-play", { state });
  }

  moveTo(x: number, y: number): void {
    if (!this.window) return;
    const display = displayForDesktopPet(this.window);
    const position = clampDesktopPetPosition({ x, y }, display.workArea);
    this.window.setPosition(position.x, position.y);
  }

  private enqueue(operation: () => Promise<void>): Promise<void> {
    const next = this.queue.then(operation, operation);
    this.queue = next.catch(() => undefined);
    return next;
  }

  private async load(binding: DesktopPetBinding, settings: DesktopPetSettings, state: DesktopPetState): Promise<void> {
    const created = this.window === null;
    const window = this.window ?? this.createWindow({ openLocalAttachment: this.options.openLocalAttachment });
    const display = displayForDesktopPet(window);
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
      window.on("moved", () => this.persistPosition(this.activeRoleId, window));
      window.on("closed", () => {
        if (this.window === window) this.window = null;
      });
    } else {
      sendLoad();
    }
    this.window = window;
  }

  private persistPosition(roleId: string, window: BrowserWindow): void {
    const display = displayForDesktopPet(window);
    const [x, y] = window.getPosition();
    const settings = this.options.getSettings();
    void this.options.saveSettings({
      ...settings,
      positions: { ...settings.positions, [`${roleId}:${display.id}`]: clampDesktopPetPosition({ x, y }, display.workArea) },
    });
  }

  private destroyWindow(): void {
    this.window?.destroy();
    this.window = null;
  }
}
