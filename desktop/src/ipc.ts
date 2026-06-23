import { BrowserWindow, dialog, ipcMain } from "electron";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { IpcMainInvokeEvent } from "electron";
import type { DesktopBridgeClient } from "./bridgeClient.js";
import { runBridgeSmoke } from "./smoke.js";
import type { WindowControlAction } from "./shared.js";

type RegisterDesktopIpcOptions = {
  bridge: DesktopBridgeClient;
  desktopRoot: string;
};

/** Registers all IPC handlers exposed through the desktop preload bridge. */
export function registerDesktopIpc({ bridge, desktopRoot }: RegisterDesktopIpcOptions): void {
  ipcMain.handle("desktop:invoke", async (_event: IpcMainInvokeEvent, request: { method: string; payload: Record<string, unknown> }) => {
    return await bridge.invoke(request);
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
  ipcMain.handle("desktop:pick-images", async (_event: IpcMainInvokeEvent, options?: { multiple?: boolean }) => {
    if (process.env.MIRA_DESKTOP_PICK_IMAGES_FIXTURE === "1") {
      const fixtureDir = resolve(desktopRoot, ".smoke-fixtures");
      mkdirSync(fixtureDir, { recursive: true });
      const avatarPath = resolve(fixtureDir, "avatar-smoke.png");
      const illustrationPath = resolve(fixtureDir, "illustration-smoke.png");
      writeFileSync(avatarPath, "avatar-smoke", { encoding: "utf8" });
      writeFileSync(illustrationPath, "illustration-smoke", { encoding: "utf8" });
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
  ipcMain.handle("desktop:smoke", async () => {
    return await runBridgeSmoke(bridge);
  });
}
