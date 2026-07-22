import type { BrowserWindow } from "electron";
import { desktopPetViewport, clampDesktopPetPosition, createDesktopPetWindow, displayForDesktopPet } from "./window.js";
import { bindDesktopPetSettings } from "./settings.js";
import type { DesktopPetBinding, DesktopPetSettings, DesktopPetState } from "./types.js";

type DesktopPetControllerOptions = {
  getSettings: () => DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: (roleId?: string) => Promise<DesktopPetBinding | null>;
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
