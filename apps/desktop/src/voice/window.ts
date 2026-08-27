import { BrowserWindow } from "electron";
import type { BrowserWindow as BrowserWindowInstance } from "electron";
import { rendererDevServerUrl, rendererVoiceDist, preloadScript } from "../paths.js";
import { attachDesktopWindowSecurity, resolveRendererEntryUrl, validateRendererDevServerUrl } from "../windowSecurity.js";

/** Hidden voice renderer plus the load lifecycle established before navigation starts. */
export type VoiceWindowSurface = {
  window: BrowserWindowInstance;
  ready: Promise<void>;
};

/** Creates the hidden, provider-agnostic capture and playback surface. */
export function createVoiceCaptureWindow(): VoiceWindowSurface {
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
      backgroundThrottling: false,
    },
  });
  let resolveReady!: () => void;
  let rejectReady!: (error: Error) => void;
  let settled = false;
  const ready = new Promise<void>((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });
  const finishLoad = (error?: Error) => {
    if (settled) return;
    settled = true;
    if (error) rejectReady(error);
    else resolveReady();
  };
  window.webContents.once("did-finish-load", () => finishLoad());
  window.webContents.once("did-fail-load", (_event, _errorCode, errorDescription) => {
    finishLoad(new Error(`语音窗口加载失败: ${errorDescription}`));
  });
  window.once("closed", () => finishLoad(new Error("语音窗口加载前已关闭")));
  attachDesktopWindowSecurity(window.webContents, {
    rendererEntryUrl: resolveRendererEntryUrl(rendererVoiceDist, rendererDevServerUrl),
    openLocalAttachment: () => undefined,
  });
  const devUrl = validateRendererDevServerUrl(rendererDevServerUrl);
  if (devUrl) {
    void window.loadURL(new URL("voice.html", devUrl).toString()).catch((error) => {
      finishLoad(error instanceof Error ? error : new Error("语音窗口加载失败"));
    });
  } else {
    void window.loadFile(rendererVoiceDist).catch((error) => {
      finishLoad(error instanceof Error ? error : new Error("语音窗口加载失败"));
    });
  }
  return { window, ready };
}
