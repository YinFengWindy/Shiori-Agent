import { BrowserWindow } from "electron";
import { attachWindowSmokeHandlers } from "./smoke.js";
import { preloadScript, rendererDevServerUrl, rendererDist } from "./paths.js";

function emitWindowState(window: BrowserWindow): void {
  window.webContents.send("desktop:event", {
    id: `window-state-${Date.now()}`,
    type: "event",
    method: "window.state",
    payload: {
      isMaximized: window.isMaximized(),
    },
  });
}

/** Creates the desktop shell window and wires renderer smoke hooks when requested. */
export function createDesktopWindow(): BrowserWindow {
  const win = new BrowserWindow({
    title: "Shiori",
    width: 1320,
    height: 860,
    minWidth: 520,
    minHeight: 680,
    frame: false,
    backgroundColor: "#f4efe6",
    webPreferences: {
      preload: preloadScript,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
    },
  });
  win.webContents.on("console-message", (details: { message: string }) => {
    if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
      console.log(`[desktop-ui-console] ${details.message}`);
    }
  });
  win.webContents.on("did-fail-load", (_event, errorCode, errorDescription) => {
    if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
      console.error(`[desktop-ui-load-fail] ${errorCode} ${errorDescription}`);
    }
  });
  win.on("maximize", () => emitWindowState(win));
  win.on("unmaximize", () => emitWindowState(win));
  if (rendererDevServerUrl) {
    void win.loadURL(rendererDevServerUrl);
  } else {
    void win.loadFile(rendererDist);
  }
  win.webContents.on("did-finish-load", () => emitWindowState(win));
  attachWindowSmokeHandlers(win);
  return win;
}
