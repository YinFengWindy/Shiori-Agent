import { BrowserWindow, dialog, ipcMain } from "electron";
import { resolve } from "node:path";
import type { IpcMainInvokeEvent } from "electron";
import { logDesktopDiagnostic } from "./diagnostics.js";
import type { DesktopBridgeClient } from "./bridgeClient.js";
import { importLocalAssets } from "./localAssetImport.js";
import type { LocalAssetRegistry } from "./localAssetRegistry.js";
import { loadSettingsData, saveSettings } from "./settings.js";
import type {
  LocalAssetOpenRequest,
  LocalAssetOpenResult,
  LocalAssetReference,
  LocalAssetTransport,
  RendererDiagnosticPayload,
  SettingsFormData,
} from "./shared.js";
import type { WindowControlAction } from "./shared.js";

type RegisterDesktopIpcOptions = {
  bridge: DesktopBridgeClient;
  desktopRoot: string;
  localAssets: LocalAssetRegistry;
  localAssetImportsRoot: string;
  openLocalAttachment: (value: string) => Promise<LocalAssetOpenResult>;
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
export function registerDesktopIpc({
  bridge,
  desktopRoot,
  localAssets,
  localAssetImportsRoot,
  openLocalAttachment,
}: RegisterDesktopIpcOptions): void {
  const dragPreviewIconPath = resolve(desktopRoot, "..", "assets", "drag-file-icon.png");

  ipcMain.handle("desktop:invoke", async (_event: IpcMainInvokeEvent, request: { method: string; payload: Record<string, unknown> }) => {
    const response = await bridge.invoke(request);
    return assetTransport(response, localAssets.grantTrustedPayload(response.payload));
  });
  ipcMain.on("desktop:start-attachment-drag", (event: IpcMainInvokeEvent, request?: { path?: unknown }) => {
    const filePath = String(request?.path ?? "").trim();
    const grant = localAssets.resolveReference(filePath);
    if (!grant) {
      return;
    }
    event.sender.startDrag({
      file: grant.canonicalPath,
      icon: dragPreviewIconPath,
    });
  });
  ipcMain.on("desktop:renderer-diagnostic", (_event: IpcMainInvokeEvent, payload?: RendererDiagnosticPayload) => {
    const diagnostic = payload ?? {
      kind: "error",
      message: "renderer emitted an empty diagnostic payload",
    };
    logDesktopDiagnostic({
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
  ipcMain.handle("desktop:bridge-status", async () => {
    return {
      running: bridge.isRunning(),
      lastError: bridge.getLastError(),
    };
  });
  ipcMain.handle("desktop:bridge-restart", async () => {
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
  ipcMain.handle("desktop:settings-read", async () => {
    return loadSettingsData();
  });
  ipcMain.handle("desktop:settings-save", async (_event: IpcMainInvokeEvent, formData: SettingsFormData) => {
    return await saveSettings(
      formData,
      async () => {
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
      },
      async () => {
        const health = await bridge.invoke({
          method: "health",
          payload: {},
        });
        return {
          ok: !health.error,
          message: health.error?.message ?? "ok",
        };
      },
    );
  });
  ipcMain.handle("desktop:window-control", (_event: IpcMainInvokeEvent, action: WindowControlAction) => {
    const [window] = BrowserWindow.getAllWindows();
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
  ipcMain.handle("desktop:window-state", () => {
    const [window] = BrowserWindow.getAllWindows();
    return {
      isMaximized: window?.isMaximized() ?? false,
      isVisible: window?.isVisible() ?? false,
    };
  });
  ipcMain.handle("desktop:pick-images", async (_event: IpcMainInvokeEvent, options?: { multiple?: boolean }) => {
    const result = await dialog.showOpenDialog({
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
  ipcMain.handle("desktop:pick-chat-attachments", async (_event: IpcMainInvokeEvent, options?: { multiple?: boolean }) => {
    const result = await dialog.showOpenDialog({
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
  ipcMain.handle("desktop:open-attachment", async (_event: IpcMainInvokeEvent, request: LocalAssetOpenRequest) => {
    const value = String(request?.url || request?.path || "").trim();
    return await openLocalAttachment(value);
  });
}
