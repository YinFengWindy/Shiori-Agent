import { BrowserWindow } from "electron";
import type { DesktopBridgeClient } from "../bridgeClient.js";
import type { InstalledDesktopPlugin, PluginOverlayContribution } from "./types.js";
import { parseInstalledDesktopPlugins } from "./types.js";
import { PluginResourceRegistry, pluginResourceScheme } from "./resourceRegistry.js";

export type PluginPageOwner = {
  pluginId: string;
  contributionId: string;
  rpcMethods: ReadonlySet<string>;
};

type HostedWindow = { window: BrowserWindow; signature: string };

/** Owns sandboxed plugin windows and their trusted sender-to-plugin identity mapping. */
export class PluginDesktopHost {
  readonly resources = new PluginResourceRegistry();
  private readonly windows = new Map<string, HostedWindow>();
  private readonly owners = new Map<object, PluginPageOwner>();

  constructor(private readonly preloadPath: string) {}

  ownerFor(sender: object): PluginPageOwner | null {
    return this.owners.get(sender) ?? null;
  }

  async syncFromBridge(bridge: DesktopBridgeClient): Promise<void> {
    const response = await bridge.invoke({ method: "plugins.installed", payload: {} });
    if (response.error) throw new Error(response.error.message);
    await this.sync(parseInstalledDesktopPlugins(response.payload.plugins));
  }

  async sync(plugins: readonly InstalledDesktopPlugin[]): Promise<void> {
    const enabled = plugins.filter((plugin) => plugin.enabled);
    this.resources.replace(enabled);
    const desired = new Map<string, { plugin: InstalledDesktopPlugin; contribution: PluginOverlayContribution; signature: string }>();
    for (const plugin of enabled) {
      for (const contribution of plugin.contributions) {
        const key = `${plugin.pluginId}:${contribution.id}`;
        desired.set(key, {
          plugin,
          contribution,
          signature: JSON.stringify({ packageDir: plugin.packageDir, contribution, rpcMethods: plugin.rpcMethods }),
        });
      }
    }
    for (const [key, hosted] of this.windows) {
      const next = desired.get(key);
      if (!next || next.signature !== hosted.signature) {
        hosted.window.destroy();
        this.windows.delete(key);
        this.owners.delete(hosted.window.webContents);
      }
    }
    for (const [key, item] of desired) {
      if (!this.windows.has(key)) this.createWindow(key, item.plugin, item.contribution, item.signature);
    }
  }

  shutdown(): void {
    for (const hosted of this.windows.values()) hosted.window.destroy();
    this.windows.clear();
    this.owners.clear();
    this.resources.replace([]);
  }

  private createWindow(key: string, plugin: InstalledDesktopPlugin, contribution: PluginOverlayContribution, signature: string): void {
    const window = new BrowserWindow({
      width: contribution.width,
      height: contribution.height,
      frame: contribution.frame,
      transparent: contribution.transparent,
      resizable: contribution.resizable,
      skipTaskbar: contribution.skipTaskbar,
      alwaysOnTop: contribution.alwaysOnTop,
      hasShadow: !contribution.transparent,
      show: false,
      webPreferences: {
        preload: this.preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        spellcheck: false,
      },
    });
    if (contribution.alwaysOnTop) {
      window.setAlwaysOnTop(true, "normal");
      window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    }
    this.owners.set(window.webContents, {
      pluginId: plugin.pluginId,
      contributionId: contribution.id,
      rpcMethods: new Set(plugin.rpcMethods.map((method) => method.method)),
    });
    this.windows.set(key, { window, signature });
    window.webContents.on("will-navigate", (event: { preventDefault(): void }, target: string) => {
      try {
        const requested = new URL(target);
        if (requested.protocol === `${pluginResourceScheme}:` && requested.hostname === plugin.pluginId) return;
      } catch {
        // Invalid navigation is denied below.
      }
      event.preventDefault();
    });
    window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    window.once("ready-to-show", () => window.showInactive());
    window.on("closed", () => {
      if (this.windows.get(key)?.window === window) this.windows.delete(key);
      this.owners.delete(window.webContents);
    });
    window.webContents.on("render-process-gone", () => {
      this.owners.delete(window.webContents);
      if (!window.isDestroyed()) window.destroy();
    });
    void window.loadURL(this.resources.entryUrl(plugin.pluginId, contribution.entrypoint));
  }
}
