/**
 * The DesktopSurface capability's vocabulary, kept dependency-free.
 *
 * A *surface* is a plugin-owned, host-created desktop window: transparent,
 * frameless and always-on-top by default. The host owns everything that only
 * the Electron main process can do — window lifecycle, screen coordinates,
 * native cursor tracking, tray entries — and knows nothing about what the
 * plugin puts inside it. Per the #181 decision recorded on the issue, plugin
 * code never runs in the main process: a plugin ships a renderer entry plus a
 * Python backend and drives its window exclusively through these primitives.
 *
 * This module has no `electron` import on purpose, so the geometry contract
 * can be asserted from the plain node:test runner the rest of the desktop
 * package uses.
 */

/** A point in screen coordinates. */
export type SurfacePoint = { x: number; y: number };

/** A display's usable region, excluding taskbars and other reserved chrome. */
export type SurfaceWorkArea = { x: number; y: number; width: number; height: number };

/** A window rectangle in screen coordinates. */
export type SurfaceBounds = { x: number; y: number; width: number; height: number };

/**
 * The fixed-size region a surface is positioned by.
 *
 * A surface's window may be taller than its body (see `SurfaceExtension`), but
 * only the body is clamped into the work area — otherwise a transient overlay
 * growing upward would drag the whole surface down the screen.
 */
export type SurfaceBody = { width: number; height: number };

/**
 * Extra window space attached to one side of the body.
 *
 * This is the generic form of "a panel that pops up above or below the
 * surface": the host grows the window and moves its origin so the body stays
 * visually put. Deciding *which* side to use, and how tall the panel is, is
 * the plugin's business — it queries `workArea` and calls `setExtension`.
 * The host has no notion of a speech bubble or any other content.
 */
export type SurfaceExtension = { side: "above" | "below"; size: number };

/** The neutral extension: window bounds equal body bounds. */
export const noSurfaceExtension: SurfaceExtension = { side: "below", size: 0 };

/** Everything a plugin declares when asking the host to create its window. */
export type SurfaceSpec = {
  /** Fixed body size; the window may exceed it only via an extension. */
  body: SurfaceBody;
  /** Defaults to true — the point of a surface is to sit over the desktop. */
  transparent?: boolean;
  /** Defaults to true. Never elevated to the screen-saver level. */
  alwaysOnTop?: boolean;
  /** Defaults to true — a surface is not an application window. */
  skipTaskbar?: boolean;
  /** Starts the surface click-through; can be toggled later. */
  clickThrough?: boolean;
};

/**
 * Construction options for a surface window.
 *
 * Kept here rather than in `window.ts` so the "transparent, frameless, always
 * on top, never node-integrated" contract is assertable without Electron.
 *
 * The host and Electron adapter reveal it only after renderer readiness and
 * the first paint, without taking focus from the user's current application.
 */
export function desktopSurfaceWindowOptions(spec: SurfaceSpec, preload: string) {
  return {
    show: false,
    width: spec.body.width,
    height: spec.body.height,
    frame: false,
    transparent: spec.transparent ?? true,
    resizable: false,
    skipTaskbar: spec.skipTaskbar ?? true,
    alwaysOnTop: spec.alwaysOnTop ?? true,
    hasShadow: false,
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
    },
  };
}
