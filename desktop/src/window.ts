import { BrowserWindow } from "electron";
import { logDesktopDiagnostic } from "./diagnostics.js";
import { attachWindowSmokeHandlers } from "./smoke.js";
import { desktopWindowIcon, preloadScript, rendererDevServerUrl, rendererDist } from "./paths.js";

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
    icon: desktopWindowIcon,
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
    logDesktopDiagnostic({
      scope: "main",
      event: "window.did-fail-load",
      payload: {
        errorCode,
        errorDescription,
      },
    });
    if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
      console.error(`[desktop-ui-load-fail] ${errorCode} ${errorDescription}`);
    }
  });
  win.on("unresponsive", () => {
    logDesktopDiagnostic({
      scope: "main",
      event: "window.unresponsive",
      payload: {},
    });
  });
  win.on("responsive", () => {
    logDesktopDiagnostic({
      scope: "main",
      event: "window.responsive",
      payload: {},
    });
  });
  win.webContents.on("render-process-gone", (_event, details) => {
    logDesktopDiagnostic({
      scope: "main",
      event: "window.render-process-gone",
      payload: {
        reason: details.reason,
        exitCode: details.exitCode,
      },
    });
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
