import type {
  SurfaceExtension,
  SurfaceInteractionTarget,
  SurfaceSpec,
  SurfaceWorkArea,
  SurfaceMenuItem,
} from "@yinfengwindy/shiori-sdk/contract";
import type { SurfacePoint } from "./contract.js";
import { DesktopSurfaceError, type DesktopSurfaceHost, type SurfaceKey } from "./host.js";

/**
 * IPC channels for the DesktopSurface capability.
 *
 * Two kinds of caller reach these:
 *
 * - **A plugin's main-window UI** (the `nav.page` / `settings.section` code
 *   registered in #179) creates and destroys its own surfaces. A surface
 *   renderer cannot create its own window, so creation has to come from
 *   somewhere already running.
 * - **A surface renderer** drives the window it is already inside — drag,
 *   release, extension, click-through. It never names a surface: the host
 *   attributes the request to whichever surface owns the sending window.
 *
 * Two different ways of naming a surface appear below, and they are not equally
 * strong:
 *
 * - `ownSurface(event)` derives the target from the **sending window's identity**.
 *   A surface renderer genuinely cannot address anything but itself this way.
 * - `readKey(payload)` takes the plugin id the caller states. Nothing verifies
 *   it, and nothing can: under the trust model recorded in #210 (install =
 *   full trust, no runtime sandbox) every plugin's main-window UI shares one
 *   renderer realm with the host, so any of it could send any payload — or
 *   reach `ipcRenderer` directly. Treat the stated id as a *convention that
 *   keeps honest bugs local*, never as a boundary, and do not add checks here
 *   that would imply otherwise.
 */

export const surfaceChannels = {
  create: "desktop:surface-create",
  destroy: "desktop:surface-destroy",
  show: "desktop:surface-show",
  hide: "desktop:surface-hide",
  workArea: "desktop:surface-work-area",
  post: "desktop:surface-post",
  setState: "desktop:surface-set-state",
  setInteraction: "desktop:surface-set-interaction",
  ready: "desktop:surface-ready",
  contextMenu: "desktop:surface-context-menu",
  activateMainWindow: "desktop:surface-activate-main-window",
  setPosition: "desktop:surface-set-position",
  setExtension: "desktop:surface-set-extension",
  setClickThrough: "desktop:surface-set-click-through",
  moveTo: "desktop:surface-move-to",
  beginDrag: "desktop:surface-begin-drag",
  endDrag: "desktop:surface-end-drag",
} as const;

/** The bits of the IPC boundary this module needs, mirroring `DesktopIpcHost`. */
export type SurfaceIpcHost = {
  handle(channel: string, listener: (event: SurfaceIpcEvent, payload: unknown) => unknown): void;
  on(channel: string, listener: (event: SurfaceIpcEvent, payload: unknown) => void): void;
  /** Resolves the id of the window that sent a request, or null when it is gone. */
  windowIdFromEvent(event: SurfaceIpcEvent): number | null;
};

export type SurfaceIpcEvent = { readonly sender: unknown };

export type RegisterSurfaceIpcOptions = {
  surfaces: DesktopSurfaceHost;
  /** Reports a refused or failed request; failures here never crash the caller. */
  onError?: (channel: string, error: unknown) => void;
};

export function registerSurfaceIpc(host: SurfaceIpcHost, options: RegisterSurfaceIpcOptions): void {
  const { surfaces } = options;
  const report = options.onError ?? (() => {});

  /** Resolves the surface that owns the sending window, for self-directed requests. */
  function ownSurface(event: SurfaceIpcEvent): SurfaceKey | null {
    return surfaces.keyForWindowId(host.windowIdFromEvent(event));
  }

  function guard<T>(channel: string, run: () => T): T | undefined {
    try {
      return run();
    } catch (error) {
      // A surface that closed between a renderer's send and its arrival is
      // ordinary, not exceptional: the renderer is gone and there is nobody to
      // tell. Never let it take the main process down.
      report(channel, error);
      return undefined;
    }
  }

  host.handle(surfaceChannels.create, (_event, payload) => {
    const request = readCreateRequest(payload);
    if (!request) throw new DesktopSurfaceError("surface 创建请求不合法");
    const anchor = surfaces.create(request.key, request.spec, request.anchor);
    // `displayId` is answered here rather than on a channel of its own so a
    // plugin that remembers a per-display position can apply it before the
    // window has painted — see `SurfaceCreateResult`.
    return { ...anchor, displayId: surfaces.displayId(request.key) };
  });

  host.handle(surfaceChannels.workArea, (_event, payload): SurfaceWorkArea => {
    const key = readKey(payload);
    if (!key) throw new DesktopSurfaceError("surface 请求缺少插件或 surface id");
    return surfaces.workArea(key);
  });

  host.handle(surfaceChannels.destroy, (_event, payload) => {
    const key = readKey(payload);
    if (key) surfaces.destroy(key);
  });

  host.on(surfaceChannels.show, (_event, payload) => {
    const key = readKey(payload);
    if (key) guard(surfaceChannels.show, () => surfaces.show(key));
  });

  host.on(surfaceChannels.hide, (_event, payload) => {
    const key = readKey(payload);
    if (key) guard(surfaceChannels.hide, () => surfaces.hide(key));
  });

  host.on(surfaceChannels.post, (_event, payload) => {
    const key = readKey(payload);
    if (key) surfaces.postMessage(key, (payload as { message?: unknown }).message);
  });

  host.on(surfaceChannels.setState, (_event, payload) => {
    const key = readKey(payload);
    if (key) surfaces.setState(key, (payload as { state?: unknown }).state);
  });

  host.on(surfaceChannels.setInteraction, (_event, payload) => {
    const key = readKey(payload);
    if (!key || !payload || typeof payload !== "object" || !("target" in payload)) return;
    const target = readInteractionTarget(payload.target);
    if (target !== undefined) guard(surfaceChannels.setInteraction, () => surfaces.setInteraction(key, target));
  });

  host.on(surfaceChannels.ready, (event) => {
    const key = ownSurface(event);
    if (key) guard(surfaceChannels.ready, () => surfaces.markReady(key));
  });

  host.on(surfaceChannels.activateMainWindow, (event) => {
    // Attributed by window identity: only a live surface may pull the main
    // window forward, so a stale renderer cannot steal focus after teardown.
    if (ownSurface(event)) surfaces.activateMainWindow();
  });

  host.handle(surfaceChannels.contextMenu, async (event, payload) => {
    const key = ownSurface(event);
    if (!key) return null;
    const items = readMenuItems(payload);
    if (!items) return null;
    return await surfaces.showContextMenu(key, items);
  });

  host.on(surfaceChannels.setPosition, (event, payload) => {
    const key = readKey(payload) ?? ownSurface(event);
    const point = readPoint(payload);
    if (key && point) guard(surfaceChannels.setPosition, () => surfaces.setPosition(key, point));
  });

  host.on(surfaceChannels.moveTo, (event, payload) => {
    const key = readKey(payload) ?? ownSurface(event);
    const point = readPoint(payload);
    const durationMs = readNumber((payload as { durationMs?: unknown }).durationMs);
    if (key && point) {
      guard(surfaceChannels.moveTo, () => surfaces.moveTo(key, point, durationMs ?? 0));
    }
  });

  host.on(surfaceChannels.setExtension, (event, payload) => {
    const key = ownSurface(event);
    const extension = readExtension(payload);
    if (key && extension) guard(surfaceChannels.setExtension, () => surfaces.setExtension(key, extension));
  });

  host.on(surfaceChannels.setClickThrough, (event, payload) => {
    const key = ownSurface(event);
    const clickThrough = (payload as { clickThrough?: unknown }).clickThrough;
    if (key && typeof clickThrough === "boolean") {
      guard(surfaceChannels.setClickThrough, () => surfaces.setClickThrough(key, clickThrough));
    }
  });

  host.on(surfaceChannels.beginDrag, (event, payload) => {
    const key = ownSurface(event);
    const offset = readPointNamed(payload, "offsetX", "offsetY");
    if (key && offset) guard(surfaceChannels.beginDrag, () => surfaces.beginDrag(key, offset));
  });

  host.on(surfaceChannels.endDrag, (event, payload) => {
    const key = ownSurface(event);
    if (!key) return;
    const velocity = readPointNamed(payload, "velocityX", "velocityY");
    guard(surfaceChannels.endDrag, () => surfaces.endDrag(key, velocity ?? undefined));
  });
}

function readKey(payload: unknown): SurfaceKey | null {
  if (payload === null || typeof payload !== "object") return null;
  const { pluginId, surfaceId } = payload as { pluginId?: unknown; surfaceId?: unknown };
  if (typeof pluginId !== "string" || !pluginId) return null;
  if (typeof surfaceId !== "string" || !surfaceId) return null;
  return { pluginId, surfaceId };
}

function readCreateRequest(
  payload: unknown,
): { key: SurfaceKey; spec: SurfaceSpec; anchor: SurfacePoint } | null {
  const key = readKey(payload);
  if (!key) return null;
  const spec = (payload as { spec?: unknown }).spec;
  if (spec === null || typeof spec !== "object") return null;
  const body = (spec as { body?: unknown }).body;
  if (body === null || typeof body !== "object") return null;
  const width = readNumber((body as { width?: unknown }).width);
  const height = readNumber((body as { height?: unknown }).height);
  if (width === null || height === null || width <= 0 || height <= 0) return null;
  const anchor = readPoint(payload) ?? { x: 0, y: 0 };
  const flags = spec as Partial<SurfaceSpec>;
  return {
    key,
    spec: {
      body: { width: Math.round(width), height: Math.round(height) },
      transparent: typeof flags.transparent === "boolean" ? flags.transparent : undefined,
      alwaysOnTop: typeof flags.alwaysOnTop === "boolean" ? flags.alwaysOnTop : undefined,
      skipTaskbar: typeof flags.skipTaskbar === "boolean" ? flags.skipTaskbar : undefined,
      clickThrough: typeof flags.clickThrough === "boolean" ? flags.clickThrough : undefined,
    },
    anchor,
  };
}

function readPoint(payload: unknown): SurfacePoint | null {
  return readPointNamed(payload, "x", "y");
}

function readPointNamed(payload: unknown, xKey: string, yKey: string): SurfacePoint | null {
  if (payload === null || typeof payload !== "object") return null;
  const source = payload as Record<string, unknown>;
  const x = readNumber(source[xKey]);
  const y = readNumber(source[yKey]);
  if (x === null || y === null) return null;
  return { x, y };
}

/**
 * Reads a context-menu request, rejecting the whole menu if any entry is
 * malformed rather than silently opening a menu with items missing — a menu
 * that is quietly one item short looks like a feature that stopped working.
 */
function readMenuItems(payload: unknown): SurfaceMenuItem[] | null {
  if (payload === null || typeof payload !== "object") return null;
  const items = (payload as { items?: unknown }).items;
  if (!Array.isArray(items) || items.length === 0) return null;
  const parsed: SurfaceMenuItem[] = [];
  for (const item of items) {
    if (item === null || typeof item !== "object") return null;
    const { id, label } = item as { id?: unknown; label?: unknown };
    if (typeof id !== "string" || !id) return null;
    if (typeof label !== "string" || !label) return null;
    parsed.push({ id, label });
  }
  return parsed;
}

function readExtension(payload: unknown): SurfaceExtension | null {
  if (payload === null || typeof payload !== "object") return null;
  const { side, size } = payload as { side?: unknown; size?: unknown };
  if (side !== "above" && side !== "below") return null;
  const resolved = readNumber(size);
  if (resolved === null) return null;
  return { side, size: resolved };
}

/** Accepts only real, finite numbers — a NaN from a renderer must never reach window bounds. */
function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Invalid declarations are rejected rather than silently retargeted. */
function readInteractionTarget(value: unknown): SurfaceInteractionTarget | null | undefined {
  if (value === null) return null;
  if (!value || typeof value !== "object" || !("roleId" in value) || !("available" in value)) return undefined;
  if (typeof value.roleId !== "string" || !value.roleId.trim() || typeof value.available !== "boolean") return undefined;
  return { roleId: value.roleId, available: value.available };
}
