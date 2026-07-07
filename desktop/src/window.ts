import { BrowserWindow } from "electron";
import { logDesktopDiagnostic } from "./diagnostics.js";
import { desktopWindowIcon, preloadScript, rendererDevServerUrl, rendererDist } from "./paths.js";

type AttachDesktopWindowLifecycleOptions = {
  shouldHideOnClose: () => boolean;
};

type ReloadDesktopRendererOptions = {
  revealAfterReload: boolean;
};

function loadDesktopRenderer(window: BrowserWindow): Promise<void> {
  if (rendererDevServerUrl) {
    return window.loadURL(rendererDevServerUrl);
  }
  return window.loadFile(rendererDist);
}

async function reloadDesktopRenderer(
  window: BrowserWindow,
  { revealAfterReload }: ReloadDesktopRendererOptions,
): Promise<void> {
  await loadDesktopRenderer(window);
  if (revealAfterReload) {
    showDesktopWindow(window);
  }
}

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

/** Creates the desktop shell window. */
export function createDesktopWindow(): BrowserWindow {
  const rendererRecoveryTimestamps: number[] = [];

  function canRecoverRenderer(now: number): boolean {
    const recentTimestamps = rendererRecoveryTimestamps.filter((timestamp) => now - timestamp < 90_000);
    rendererRecoveryTimestamps.splice(0, rendererRecoveryTimestamps.length, ...recentTimestamps);
    return recentTimestamps.length < 3;
  }

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
    if (details.reason === "clean-exit") {
      return;
    }
    const now = Date.now();
    if (!canRecoverRenderer(now)) {
      logDesktopDiagnostic({
        scope: "main",
        event: "window.render-process-recovery-skipped",
        payload: {
          reason: details.reason,
          exitCode: details.exitCode,
          note: "renderer crashed too many times in a short window",
        },
      });
      return;
    }
    rendererRecoveryTimestamps.push(now);
    const revealAfterReload = win.isVisible();
    logDesktopDiagnostic({
      scope: "main",
      event: "window.render-process-recovery-started",
      payload: {
        reason: details.reason,
        exitCode: details.exitCode,
        revealAfterReload,
      },
    });
    setTimeout(() => {
      void reloadDesktopRenderer(win, { revealAfterReload }).then(() => {
        logDesktopDiagnostic({
          scope: "main",
          event: "window.render-process-recovery-finished",
          payload: {
            reason: details.reason,
            exitCode: details.exitCode,
          },
        });
      }).catch((error) => {
        logDesktopDiagnostic({
          scope: "main",
          event: "window.render-process-recovery-failed",
          payload: {
            reason: details.reason,
            exitCode: details.exitCode,
            error,
          },
        });
      });
    }, 350);
  });
  win.on("maximize", () => emitWindowState(win));
  win.on("unmaximize", () => emitWindowState(win));
  void loadDesktopRenderer(win);
  win.webContents.on("did-finish-load", () => emitWindowState(win));
  return win;
}

/** Restores a hidden desktop window and brings it back to the foreground. */
export function showDesktopWindow(window: BrowserWindow): void {
  if (window.isMinimized()) {
    window.restore();
  }
  if (!window.isVisible()) {
    window.show();
  }
  window.focus();
}

/** Keeps the desktop renderer alive when the user closes into the tray. */
export function attachDesktopWindowLifecycle(
  window: BrowserWindow,
  { shouldHideOnClose }: AttachDesktopWindowLifecycleOptions,
): void {
  window.on("close", (event: { preventDefault(): void }) => {
    if (!shouldHideOnClose()) {
      return;
    }
    event.preventDefault();
    window.hide();
  });
}
