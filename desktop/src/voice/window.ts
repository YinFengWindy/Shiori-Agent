import { BrowserWindow } from "electron";
import { rendererDevServerUrl, rendererVoiceDist, preloadScript } from "../paths.js";
import { attachDesktopWindowSecurity, resolveRendererEntryUrl, validateRendererDevServerUrl } from "../windowSecurity.js";

/** Creates the hidden, provider-agnostic microphone capture surface. */
export function createVoiceCaptureWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1,
    height: 1,
    show: false,
    frame: false,
    resizable: false,
    skipTaskbar: true,
    webPreferences: {
      preload: preloadScript,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
    },
  });
  attachDesktopWindowSecurity(window.webContents, {
    rendererEntryUrl: resolveRendererEntryUrl(rendererVoiceDist, rendererDevServerUrl),
    openLocalAttachment: () => undefined,
  });
  const devUrl = validateRendererDevServerUrl(rendererDevServerUrl);
  if (devUrl) {
    void window.loadURL(new URL("voice.html", devUrl).toString());
  } else {
    void window.loadFile(rendererVoiceDist);
  }
  return window;
}
