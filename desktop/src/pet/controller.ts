import type { BrowserWindow } from "electron";
import { desktopPetViewport, clampDesktopPetPosition, createDesktopPetWindow, displayForDesktopPet } from "./window.js";
import type { DesktopPetBinding, DesktopPetPosition, DesktopPetSettings, DesktopPetState } from "./types.js";

type DesktopPetControllerOptions = {
  getSettings: () => DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: (roleId: string, packageId: string) => Promise<DesktopPetBinding | null>;
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

  enable(): Promise<void> {
    return this.enqueue(async () => {
      const settings = this.options.getSettings();
      if (!settings.roleId || !settings.packageId) throw new Error("桌宠尚未绑定角色和素材包");
      const binding = await this.options.resolveBinding(settings.roleId, settings.packageId);
      if (!binding) throw new Error("桌宠绑定已失效");
      await this.load(binding, settings, "idle");
      await this.options.saveSettings({ ...settings, enabled: true });
    });
  }

  disable(): Promise<void> {
    return this.enqueue(async () => {
      this.destroyWindow();
      await this.options.saveSettings({ ...this.options.getSettings(), enabled: false });
    });
  }

  updateBinding(roleId: string, packageId: string): Promise<void> {
    return this.enqueue(async () => {
      const binding = await this.options.resolveBinding(roleId, packageId);
      if (!binding) throw new Error("桌宠绑定无效");
      const current = this.options.getSettings();
      const next = { ...current, roleId: binding.roleId, packageId: binding.package.id };
      if (current.enabled) await this.load(binding, next, "idle");
      await this.options.saveSettings(next);
    });
  }

  restore(): Promise<void> {
    const settings = this.options.getSettings();
    return settings.enabled ? this.enable() : Promise.resolve();
  }

  play(state: DesktopPetState): void {
    this.window?.webContents.send("desktop:pet-play", { state });
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
