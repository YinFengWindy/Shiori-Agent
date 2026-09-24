import { createPluginCommunicationLifecycle } from "../plugins/communicationLifecycle.js";
import { randomUUID } from "node:crypto";
import type {
  BrowserWindow,
  IpcMain,
  OpenDialogOptions,
  OpenDialogReturnValue,
  WebContents,
} from "electron";
import type { logDesktopDiagnostic } from "../diagnostics.js";
import type { DesktopBridgeClient } from "./bridgeClient.js";
import type { PluginUiResources } from "../plugins/uiResources.js";
import { activePluginIds } from "../plugins/activePluginIds.js";
import { importLocalAssets } from "../assets/localAssetImport.js";
import type { LocalAssetRegistry } from "../assets/localAssetRegistry.js";
import { pickNativeFiles } from "./nativeFilePicker.js";
import { stagePickedFiles } from "../assets/pickedFileStaging.js";
import { maxLocalAssetBytes } from "../assets/localAssetContract.js";
import { applyRuntimeSettings, readRuntimeSettings } from "../settingsRuntime.js";
import type { BrowserVoiceRecorder } from "../voice/recorder.js";
import type { DesktopVoiceController } from "../voice/controller.js";
import type { BrowserVoicePlayback } from "../voice/playback.js";
import type { registerVoiceIpc } from "../voice/ipc.js";
import { openExternalLink } from "../externalLinks.js";
import type {
  LocalAssetOpenRequest,
  LocalAssetOpenResult,
  LocalAssetReference,
  LocalAssetTransport,
  RendererDiagnosticPayload,
  SettingsFormData,
  SettingsSaveOptions,
} from "./shared.js";
import type { WindowControlAction } from "./shared.js";

/**
 * Main-process capabilities the IPC boundary needs.
 *
 * Everything that would otherwise be reached through a module-level `electron`
 * import lives here, so this module stays importable — and therefore testable —
 * outside an Electron process. `ipc.ts` supplies the production implementation.
 */
export type DesktopIpcHost = {
  handle(channel: string, listener: Parameters<IpcMain["handle"]>[1]): void;
  on(channel: string, listener: Parameters<IpcMain["on"]>[1]): void;
  /** Resolves the window that sent the request, so handlers never act on an arbitrary one. */
  windowFromWebContents(sender: WebContents): BrowserWindow | null;
  showOpenDialog(options: OpenDialogOptions): Promise<OpenDialogReturnValue>;
  openExternal(url: string): Promise<void>;
  logDiagnostic: typeof logDesktopDiagnostic;
  dragFileIcon: string;
  registerVoiceIpc: typeof registerVoiceIpc;
};

export type RegisterDesktopIpcOptions = {
  bridge: DesktopBridgeClient;
  /** Main-process grants attached to the same authoritative plugins.list response. */
  pluginUiResources?: PluginUiResources;
  localAssets: LocalAssetRegistry;
  localAssetImportsRoot: string;
  openLocalAttachment: (value: string) => Promise<LocalAssetOpenResult>;
  /** Whether a sending window is the pet's surface, supplied by `main.ts`. */
  isPetWindow: (window: { readonly id: number } | null) => boolean;
  /**
   * Notified once per plugin id that just left the admitted-active set
   * between two `plugins.list` responses — disabled, failed, or rolled back
   * by an activation-report rollback (#262). `main.ts` wires this to
   * `DesktopSurfaceHost.destroyAllForPlugin`: nothing else in the main
   * process is told a plugin stopped, so a surface it opened would otherwise
   * outlive it (see `host.ts`'s `destroyAllForPlugin` docstring — previously
   * only unit-tested, never actually called in production).
   */
  onPluginDeactivated?: (pluginId: string) => void;
  voiceRecorder: BrowserVoiceRecorder;
  voiceController: DesktopVoiceController;
  voicePlayback: BrowserVoicePlayback;
  onVoiceSettingsChanged?: () => void;
  /**
   * Restarts the whole application (quit, then launch again), supplied by
   * `main.ts`. Exposed so changes that only take effect on the next launch
   * — plugin installs, updates, uninstalls, trust — can be applied from the
   * page that announced them.
   */
  relaunchApp: () => void;
};

function assetTransport<T>(value: T, assets: LocalAssetReference[]): LocalAssetTransport<T> {
  return { value, assets };
}

async function importPickerSelection(
  paths: string[],
  importsRoot: string,
  localAssets: LocalAssetRegistry,
): Promise<LocalAssetTransport<string[]>> {
  const importedPaths = await importLocalAssets(paths, importsRoot);
  const assets: LocalAssetReference[] = [];
  for (const path of importedPaths) {
    const reference = localAssets.grantPath(path);
    if (!reference) {
      throw new Error("imported local asset is outside the trusted workspace");
    }
    assets.push(reference);
  }
  return assetTransport(importedPaths, assets);
}

/** Registers all IPC handlers exposed through the desktop preload bridge. */
export function registerDesktopIpcHandlers(
  host: DesktopIpcHost,
  {
    bridge,
    pluginUiResources,
    localAssets,
    localAssetImportsRoot,
    openLocalAttachment,
    isPetWindow,
    voiceRecorder,
    voiceController,
    voicePlayback,
    onVoiceSettingsChanged,
    onPluginDeactivated,
    relaunchApp,
  }: RegisterDesktopIpcOptions,
): void {
  const applicationSessionId = randomUUID();
  const attributePluginCommunication = createPluginCommunicationLifecycle(bridge);
  let pluginListTail = Promise.resolve();
  // Previous `plugins.list` snapshot's admitted-active ids, so a roster that
  // just dropped one plugin (disabled, failed, or rolled back — #262) can
  // notify `onPluginDeactivated` for exactly the ids that left, not the ones
  // that were already inactive last time.
  let previouslyActivePluginIds = new Set<string>();
  host.handle("desktop:application-session-id", () => applicationSessionId);
  host.handle("desktop:invoke", async (_event, request: { method: string; payload: Record<string, unknown> }) => {
    const invoke = async () => {
      const response = await bridge.invoke(await attributePluginCommunication(_event.sender, request));
      if (request.method === "plugins.list" && !response.error) {
        if (pluginUiResources && Array.isArray(response.payload.plugins)) {
          // One admit() pass grants (or refuses) `ui`, `background` and `surface`
          // together, tagged by kind; each sibling field below picks its own kind
          // back out and drops the tag, so every consumer keeps the plain
          // `RuntimePluginUi` shape it already expects.
          const entries = await pluginUiResources.admit(response.payload.plugins);
          const grantFor = (pluginId: unknown, kind: "ui" | "background" | "surface") => {
            const entry = entries.find((candidate) => candidate.pluginId === pluginId && candidate.kind === kind);
            if (!entry) return undefined;
            const base = { pluginId: entry.pluginId, entry: entry.entry, css: entry.css, activationToken: entry.activationToken };
            return entry.error === undefined ? base : { ...base, error: entry.error };
          };
          response.payload.plugins = response.payload.plugins.map((plugin) => ({
            ...plugin,
            renderer_ui: grantFor(plugin.id, "ui"),
            renderer_background: grantFor(plugin.id, "background"),
            renderer_surface: grantFor(plugin.id, "surface"),
          }));
        }
        if (Array.isArray(response.payload.plugins)) {
          // Every renderer window independently refetches `plugins.list` and
          // tears down its own now-stale UI/background contribution when a
          // plugin drops out (see `runtimePluginUiSynchronization.ts`,
          // `PluginBackgroundHost.reconcile`). A surface window is different:
          // it is a main-process `BrowserWindow` nothing else owns (built-in
          // or external plugin alike), so this is the one place that ever
          // sees consecutive rosters to diff (#262).
          const nowActive = activePluginIds(response.payload.plugins as { id: string; enabled: boolean; state: string }[]);
          for (const pluginId of previouslyActivePluginIds) {
            if (!nowActive.has(pluginId)) onPluginDeactivated?.(pluginId);
          }
          previouslyActivePluginIds = nowActive;
        }
      }
      return assetTransport(response, localAssets.grantTrustedPayload(response.payload));
    };
    if (request.method !== "plugins.list") return invoke();
    // All renderer windows share grants; serialize roster reads together with admission.
    const pending = pluginListTail.then(invoke);
    pluginListTail = pending.then(() => undefined, () => undefined);
    return pending;
  });
  host.on("desktop:start-attachment-drag", (event, request?: { path?: unknown }) => {
    const filePath = String(request?.path ?? "").trim();
    const grant = localAssets.resolveReference(filePath);
    if (!grant) {
      return;
    }
    event.sender.startDrag({
      file: grant.canonicalPath,
      icon: host.dragFileIcon,
    });
  });
  host.on("desktop:renderer-diagnostic", (_event, payload?: RendererDiagnosticPayload) => {
    const diagnostic = payload ?? {
      kind: "error",
      message: "renderer emitted an empty diagnostic payload",
    };
    host.logDiagnostic({
      scope: "renderer",
      event: `renderer.${diagnostic.kind}`,
      payload: {
        message: diagnostic.message,
        stack: diagnostic.stack,
        componentStack: diagnostic.componentStack,
        filename: diagnostic.filename,
        lineno: diagnostic.lineno,
        colno: diagnostic.colno,
        details: diagnostic.details ?? {},
      },
    });
  });
  host.handle("desktop:bridge-status", async () => {
    return {
      running: bridge.isRunning(),
      lastError: bridge.getLastError(),
    };
  });
  host.handle("desktop:bridge-restart", async () => {
    try {
      await bridge.restart();
      return {
        ok: true,
        running: bridge.isRunning(),
        lastError: bridge.getLastError(),
      };
    } catch (error) {
      return {
        ok: false,
        running: false,
        lastError: String(error),
      };
    }
  });
  host.handle("desktop:app-relaunch", (event) => {
    // Plugin surfaces (the pet) share this preload; restarting the app is a
    // decision for the main window only.
    if (isPetWindow(host.windowFromWebContents(event.sender))) return false;
    relaunchApp();
    return true;
  });
  host.handle("desktop:settings-read", async () => {
    return readRuntimeSettings(bridge);
  });
  host.handle("desktop:settings-save", async (_event, formData: SettingsFormData, options?: SettingsSaveOptions) => {
    const result = await applyRuntimeSettings(bridge, formData, options);
    if (result.ok) onVoiceSettingsChanged?.();
    return result;
  });
  host.handle("desktop:window-control", (event, action: WindowControlAction) => {
    const window = host.windowFromWebContents(event.sender);
    if (!window) {
      return;
    }
    if (action === "minimize") {
      window.minimize();
      return;
    }
    if (action === "toggleMaximize") {
      if (window.isMaximized()) {
        window.unmaximize();
        return;
      }
      window.maximize();
      return;
    }
    if (action === "close") {
      window.close();
    }
  });
  host.handle("desktop:window-state", (event) => {
    const window = host.windowFromWebContents(event.sender);
    return {
      isMaximized: window?.isMaximized() ?? false,
      isVisible: window?.isVisible() ?? false,
    };
  });
  host.handle("desktop:pick-images", async (_event, options?: { multiple?: boolean }) => {
    const result = await host.showOpenDialog({
      properties: options?.multiple ? ["openFile", "multiSelections"] : ["openFile"],
      filters: [
        {
          name: "Images",
          extensions: ["png", "jpg", "jpeg", "webp", "gif"],
        },
      ],
    });
    if (result.canceled) {
      return assetTransport([], []);
    }
    return await importPickerSelection(result.filePaths, localAssetImportsRoot, localAssets);
  });
  host.handle("desktop:pick-role-card", async () => {
    const result = await host.showOpenDialog({
      properties: ["openFile"],
      filters: [{ name: "Role cards", extensions: ["png", "apng", "json", "charx"] }],
    });
    if (result.canceled) return assetTransport([], []);
    const stagedPaths = await stagePickedFiles(result.filePaths, localAssetImportsRoot, {
      namespace: "role-cards", filters: [{ name: "Role cards", extensions: ["png", "apng", "json", "charx"] }],
      maxFileBytes: maxLocalAssetBytes,
    });
    const assets = stagedPaths.map((path) => {
      const reference = localAssets.grantPath(path);
      if (!reference) throw new Error("staged role card is outside the trusted workspace");
      return reference;
    });
    return assetTransport(stagedPaths, assets);
  });
  // The pet's ready / bubble-height / drag / open / context-menu channels are
  // gone. Since #181-B the pet is a plugin surface, so those requests arrive on
  // the generic DesktopSurface channels in `src/surface/ipc.ts`, where the host
  // attributes them by the sending window's identity rather than by a
  // pet-specific check here.
  host.registerVoiceIpc({ isPetWindow, voiceRecorder, voiceController, voicePlayback });
  host.handle("desktop:pick-chat-attachments", async (_event, options?: { multiple?: boolean }) => {
    const result = await host.showOpenDialog({
      properties: options?.multiple ? ["openFile", "multiSelections"] : ["openFile"],
      filters: [
        {
          name: "Chat Attachments",
          extensions: ["png", "jpg", "jpeg", "webp", "gif", "md", "txt"],
        },
      ],
    });
    if (result.canceled) {
      return assetTransport([], []);
    }
    return await importPickerSelection(result.filePaths, localAssetImportsRoot, localAssets);
  });
  host.handle("desktop:pick-files", (_event, options: unknown) =>
    pickNativeFiles(options, localAssetImportsRoot, (dialogOptions) => host.showOpenDialog(dialogOptions)));
  host.handle("desktop:open-attachment", async (_event, request: LocalAssetOpenRequest) => {
    const value = String(request?.url || request?.path || "").trim();
    return await openLocalAttachment(value);
  });
  host.handle("desktop:open-external", async (_event, request?: { url?: unknown }) => {
    return await openExternalLink(String(request?.url ?? ""), (url) => host.openExternal(url));
  });
}
