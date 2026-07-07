import { BrowserWindow, dialog, ipcMain } from "electron";
import { copyFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import type { IpcMainInvokeEvent } from "electron";
import { logDesktopDiagnostic } from "./diagnostics.js";
import type { DesktopBridgeClient } from "./bridgeClient.js";
import { runBridgeSmoke } from "./smoke.js";
import { loadChannelRoleBindings, loadSettingsData, saveSettings } from "./settings.js";
import type { RendererDiagnosticPayload, SettingsChannelRoleBinding, SettingsFormData } from "./shared.js";
import type { WindowControlAction } from "./shared.js";

type RegisterDesktopIpcOptions = {
  bridge: DesktopBridgeClient;
  desktopRoot: string;
};

/** Registers all IPC handlers exposed through the desktop preload bridge. */
export function registerDesktopIpc({ bridge, desktopRoot }: RegisterDesktopIpcOptions): void {
  const dragPreviewIconPath = resolve(desktopRoot, "..", "assets", "drag-file-icon.png");

  ipcMain.handle("desktop:invoke", async (_event: IpcMainInvokeEvent, request: { method: string; payload: Record<string, unknown> }) => {
    return await bridge.invoke(request);
  });
  ipcMain.on("desktop:start-attachment-drag", (event: IpcMainInvokeEvent, request?: { path?: unknown }) => {
    const filePath = String(request?.path ?? "").trim();
    if (!filePath || !isAbsolute(filePath) || !existsSync(filePath)) {
      return;
    }
    event.sender.startDrag({
      file: filePath,
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
  ipcMain.handle("desktop:channel-role-bindings-read", async () => {
    const response = await bridge.invoke({
      method: "roles.bindings.list",
      payload: {},
    });
    if (response.error) {
      throw new Error(response.error.message);
    }
    const bindings = Array.isArray(response.payload.bindings) ? response.payload.bindings as Array<Record<string, unknown>> : [];
    return loadChannelRoleBindings(
      bindings.map((binding) => ({
        channel: String(binding.channel ?? ""),
        chatId: String(binding.chat_id ?? binding.chatId ?? ""),
        roleId: String(binding.role_id ?? binding.roleId ?? ""),
      })),
    );
  });
  ipcMain.handle("desktop:channel-role-bindings-save", async (_event: IpcMainInvokeEvent, bindings: SettingsChannelRoleBinding[]) => {
    const response = await bridge.invoke({
      method: "roles.bindings.replace",
      payload: {
        bindings: Array.isArray(bindings)
          ? bindings.map((binding) => ({
            channel: String(binding.channel ?? "").trim(),
            chat_id: String(binding.chatId ?? "").trim(),
            role_id: String(binding.roleId ?? "").trim(),
          }))
          : [],
      },
    });
    if (response.error) {
      throw new Error(response.error.message);
    }
    const nextBindings = Array.isArray(response.payload.bindings) ? response.payload.bindings as Array<Record<string, unknown>> : [];
    return loadChannelRoleBindings(
      nextBindings.map((binding) => ({
        channel: String(binding.channel ?? ""),
        chatId: String(binding.chat_id ?? ""),
        roleId: String(binding.role_id ?? ""),
      })),
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
    if (process.env.MIRA_DESKTOP_PICK_IMAGES_FIXTURE === "1") {
      const fixtureDir = resolve(desktopRoot, ".smoke-fixtures");
      mkdirSync(fixtureDir, { recursive: true });
      const sourceImagePath = resolve(desktopRoot, "..", "assets", "akashic-qq.jpg");
      const avatarPath = resolve(fixtureDir, "avatar-smoke.jpg");
      const illustrationPath = resolve(fixtureDir, "illustration-smoke.jpg");
      copyFileSync(sourceImagePath, avatarPath);
      copyFileSync(sourceImagePath, illustrationPath);
      return options?.multiple ? [avatarPath, illustrationPath] : [avatarPath];
    }
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
      return [];
    }
    return result.filePaths;
  });
  ipcMain.handle("desktop:pick-chat-attachments", async (_event: IpcMainInvokeEvent, options?: { multiple?: boolean }) => {
    if (process.env.MIRA_DESKTOP_PICK_IMAGES_FIXTURE === "1") {
      const fixtureDir = resolve(desktopRoot, ".smoke-fixtures");
      mkdirSync(fixtureDir, { recursive: true });
      const sourceImagePath = resolve(desktopRoot, "..", "assets", "akashic-qq.jpg");
      const imagePath = resolve(fixtureDir, "chat-image-smoke.jpg");
      const textPath = resolve(fixtureDir, "chat-note-smoke.md");
      copyFileSync(sourceImagePath, imagePath);
      writeFileSync(textPath, "# smoke attachment\n\nfixture note\n", { encoding: "utf-8" });
      return options?.multiple ? [imagePath, textPath] : [imagePath];
    }
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
      return [];
    }
    return result.filePaths;
  });
  ipcMain.handle("desktop:smoke", async () => {
    return await runBridgeSmoke(bridge);
  });
}
