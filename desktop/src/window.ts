import { BrowserWindow } from "electron";
import { attachWindowSmokeHandlers } from "./smoke.js";
import { preloadScript, rendererDist } from "./paths.js";

/** Creates the desktop shell window and wires renderer smoke hooks when requested. */
export function createDesktopWindow(): BrowserWindow {
  const win = new BrowserWindow({
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
      sandbox: false
    },
  });
  win.webContents.on("console-message", (_event, _level, message) => {
    if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
      console.log(`[desktop-ui-console] ${message}`);
    }
  });
  win.webContents.on("did-fail-load", (_event, errorCode, errorDescription) => {
    if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
      console.error(`[desktop-ui-load-fail] ${errorCode} ${errorDescription}`);
    }
  });
  void win.loadFile(rendererDist);
  attachWindowSmokeHandlers(win);
  return win;
}
