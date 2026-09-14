import { BrowserWindow, Menu, screen } from "electron";
import { rendererDevServerUrl, rendererSurfaceDist, preloadScript } from "../paths.js";
import {
  attachDesktopWindowSecurity,
  resolveRendererEntryUrl,
  validateRendererDevServerUrl,
} from "../windowSecurity.js";
import { desktopSurfaceWindowOptions, type SurfaceSpec, type SurfaceWorkArea } from "./contract.js";
import type { SurfaceKey, SurfaceMenuItem, SurfaceWindowHandle } from "./host.js";
import { surfaceQueryString } from "./entry.js";

/**
 * The Electron half of the DesktopSurface capability.
 *
 * Everything here needs a live Electron process, so it is kept apart from
 * `host.ts` — which holds all the behaviour worth testing and is deliberately
 * importable from the plain node:test runner.
 */

/**
 * Creates one plugin-owned surface window.
 *
 * Every surface loads the *same* host-owned renderer entry, told which plugin
 * it belongs to through the query string. Giving each plugin its own HTML
 * entry would mean editing `renderer/vite.config.ts` for every new plugin that
 * wants a window — which is exactly the build-time coupling #181 removes (the
 * pet's hardcoded `pet.html` entry being the current example).
 */
export function createDesktopSurfaceWindow(
  key: SurfaceKey,
  spec: SurfaceSpec,
  options: { openLocalAttachment: (url: string) => Promise<unknown> | unknown },
): SurfaceWindowHandle {
  const window = new BrowserWindow(desktopSurfaceWindowOptions(spec, preloadScript));
  const handle = adaptSurfaceWindow(window);
  window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  attachDesktopWindowSecurity(window.webContents, {
    rendererEntryUrl: resolveRendererEntryUrl(rendererSurfaceDist, rendererDevServerUrl),
    openLocalAttachment: options.openLocalAttachment,
  });
  const query = surfaceQueryString(key);
  const devUrl = validateRendererDevServerUrl(rendererDevServerUrl);
  if (devUrl) {
    const url = new URL("surface.html", devUrl);
    url.search = query;
    void window.loadURL(url.toString());
  } else {
    void window.loadFile(rendererSurfaceDist, { search: query });
  }
  return handle;
}

/** Wraps a `BrowserWindow` in the narrow handle `DesktopSurfaceHost` depends on. */
export function adaptSurfaceWindow(window: BrowserWindow): SurfaceWindowHandle {
  let painted = false;
  let visible = false;
  // ready-to-show is only a paint signal, not permission to reveal a surface.
  // hide() must also cancel a show requested before that signal arrives.
  window.once("ready-to-show", () => {
    painted = true;
    if (visible && !window.isDestroyed()) window.showInactive();
  });
  return {
    id: window.id,
    setBounds: (bounds) => window.setBounds(bounds),
    getBounds: () => window.getBounds(),
    isDestroyed: () => window.isDestroyed(),
    destroy: () => window.destroy(),
    showInactive: () => {
      visible = true;
      if (painted) window.showInactive();
    },
    hide: () => { visible = false; window.hide(); },
    setIgnoreMouseEvents: (ignore, ignoreOptions) => window.setIgnoreMouseEvents(ignore, ignoreOptions),
    send: (channel, payload) => {
      if (!window.isDestroyed()) window.webContents.send(channel, payload);
    },
    onClosed: (listener) => window.on("closed", listener),
  };
}

/** Resolves the work area of the display a surface currently sits on. */
export function workAreaForSurface(handle: SurfaceWindowHandle): SurfaceWorkArea {
  return displayForSurface(handle).workArea;
}

/**
 * Stable identity of the display a surface currently sits on.
 *
 * Callers remembering a per-display position need identity rather than the
 * work-area rectangle, which changes when a taskbar moves and can be identical
 * across two displays.
 */
export function displayIdForSurface(handle: SurfaceWindowHandle): string {
  return String(displayForSurface(handle).id);
}

function displayForSurface(handle: SurfaceWindowHandle) {
  const window = BrowserWindow.fromId(handle.id);
  return window && !window.isDestroyed()
    ? screen.getDisplayMatching(window.getBounds())
    : screen.getPrimaryDisplay();
}

/** The native cursor location, which only the main process can read. */
export function cursorScreenPoint() {
  return screen.getCursorScreenPoint();
}

/**
 * Opens a native context menu over a surface and resolves the chosen item's id.
 *
 * Resolves `null` when the menu closes without a choice — Electron reports a
 * dismissal only through the `menu-will-close` event, not through the click
 * callbacks, so the promise has to be settled from both sides or a plugin
 * awaiting it would hang forever on an Escape key.
 */
export function showSurfaceContextMenu(
  handle: SurfaceWindowHandle,
  items: SurfaceMenuItem[],
): Promise<string | null> {
  const window = BrowserWindow.fromId(handle.id);
  if (!window || window.isDestroyed()) return Promise.resolve(null);
  return new Promise((resolve) => {
    let settled = false;
    const settle = (value: string | null) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const menu = Menu.buildFromTemplate(
      items.map((item) => ({ label: item.label, click: () => settle(item.id) })),
    );
    menu.once("menu-will-close", () => {
      // Fires before a click callback does, so defer the dismissal until the
      // click (if any) has had its turn.
      setImmediate(() => settle(null));
    });
    menu.popup({ window });
  });
}
