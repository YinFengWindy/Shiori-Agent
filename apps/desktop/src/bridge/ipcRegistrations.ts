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
  voiceRecorder: BrowserVoiceRecorder;
  voiceController: DesktopVoiceController;
  voicePlayback: BrowserVoicePlayback;
  onVoiceSettingsChanged?: () => void;
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
  }: RegisterDesktopIpcOptions,
): void {
  const applicationSessionId = randomUUID();
  const attributePluginCommunication = createPluginCommunicationLifecycle(bridge);
  let pluginListTail = Promise.resolve();
  host.handle("desktop:application-session-id", () => applicationSessionId);
  host.handle("desktop:invoke", async (_event, request: { method: string; payload: Record<string, unknown> }) => {
    const invoke = async () => {
      const response = await bridge.invoke(await attributePluginCommunication(_event.sender, request));
      if (request.method === "plugins.list" && !response.error && pluginUiResources) {
        const entries = await pluginUiResources.admit(response.payload.plugins);
        if (Array.isArray(response.payload.plugins)) {
          response.payload.plugins = response.payload.plugins.map((plugin) => ({
            ...plugin, renderer_ui: entries.find((entry) => entry.pluginId === plugin.id),
          }));
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
