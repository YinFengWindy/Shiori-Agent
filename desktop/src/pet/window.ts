import { BrowserWindow, screen } from "electron";
import { rendererDevServerUrl, rendererPetDist, preloadScript } from "../paths.js";
import { attachDesktopWindowSecurity, resolveRendererEntryUrl, validateRendererDevServerUrl } from "../windowSecurity.js";
import type { DesktopPetPosition } from "./types.js";

export const desktopPetViewport = { width: 192, height: 208 };

/** Clamps the whole fixed pet viewport inside a display work area. */
export function clampDesktopPetPosition(position: DesktopPetPosition, workArea: { x: number; y: number; width: number; height: number }): DesktopPetPosition {
  return {
    x: Math.min(Math.max(position.x, workArea.x), workArea.x + workArea.width - desktopPetViewport.width),
    y: Math.min(Math.max(position.y, workArea.y), workArea.y + workArea.height - desktopPetViewport.height),
  };
}

/** Creates the fixed transparent desktop-pet surface without loading the full application renderer. */
export function createDesktopPetWindow(options: { openLocalAttachment: (url: string) => Promise<unknown> | unknown }): BrowserWindow {
  const window = new BrowserWindow({
    width: desktopPetViewport.width,
    height: desktopPetViewport.height,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    webPreferences: {
      preload: preloadScript,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
    },
  });
  window.setAlwaysOnTop(true, "screen-saver");
  window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  attachDesktopWindowSecurity(window.webContents, {
    rendererEntryUrl: resolveRendererEntryUrl(rendererPetDist, rendererDevServerUrl),
    openLocalAttachment: options.openLocalAttachment,
  });
  const devUrl = validateRendererDevServerUrl(rendererDevServerUrl);
  if (devUrl) {
    void window.loadURL(new URL("pet.html", devUrl).toString());
  } else {
    void window.loadFile(rendererPetDist);
  }
  return window;
}

/** Uses the display nearest a window, falling back to the primary display when it is unavailable. */
export function displayForDesktopPet(window: BrowserWindow | null) {
  return window ? screen.getDisplayMatching(window.getBounds()) : screen.getPrimaryDisplay();
}
