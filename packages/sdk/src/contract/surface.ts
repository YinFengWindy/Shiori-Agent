/**
 * The DesktopSurface capability's contract (#181): a *surface* is a
 * plugin-owned, host-created desktop window — transparent, frameless and
 * always-on-top by default. The host owns the window (lifecycle, screen
 * coordinates, cursor tracking) and knows nothing about what the plugin draws
 * in it; the plugin drives it only through these shapes.
 *
 * React- and DOM-free, so the Electron main process and preload share the same
 * definitions through `@shiori/sdk/contract`.
 */
import type { PluginRpcClient } from "../rpc";

/** A display's usable region in screen coordinates, excluding taskbars and other reserved chrome. */
export type SurfaceWorkArea = { x: number; y: number; width: number; height: number };

/**
 * Where a surface's body ended up after the host clamped and settled it: its
 * anchor, where the body sits inside its own window, and the work area it was
 * clamped into.
 */
export type SurfacePlacement = {
  anchor: { x: number; y: number };
  bodyOffset: { x: number; y: number };
  workArea: SurfaceWorkArea;
};

/**
 * Extra window space attached to one side of the body: the host grows the
 * window and moves its origin so the body stays visually put. Which side and
 * how tall is the plugin's business (it reads the work area and decides).
 */
export type SurfaceExtension = { side: "above" | "below"; size: number };

/** One entry of the native context menu a surface can ask the host to open. */
export type SurfaceMenuItem = { id: string; label: string };

/** Everything a plugin declares when asking the host to create one of its windows. */
export type SurfaceSpec = {
  /** Fixed body size; the window may exceed it only via an extension. */
  body: { width: number; height: number };
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
 * Where a freshly created surface landed, and which display it landed on.
 *
 * `displayId` rides along with the creation result so a plugin that remembers
 * a position per display can pick the remembered anchor before the surface
 * has painted anything, without a visible jump from a second round trip.
 */
export type SurfaceCreateResult = { x: number; y: number; displayId: string };

/**
 * Why a surface came to rest. Only some reasons mean the user (or a role)
 * moved it: growing a panel or replaying state on reload lands the surface
 * where it already was, and persisting on those would rewrite stored state
 * every time a bubble appears.
 */
export type SurfaceSettleReason =
  | "create"
  | "position"
  | "extension"
  | "drag"
  | "momentum"
  | "move"
  | "ready";

/**
 * The self-directed half of the DesktopSurface capability, handed to a
 * plugin's surface component.
 *
 * Every call acts on the window the component is already rendering inside —
 * there is no surface id to pass, because the host attributes the request by
 * window identity rather than by anything the renderer claims.
 */
export type SurfaceHandle = {
  /** Starts host-driven cursor following; `offset` is where inside the body the pointer grabbed. */
  beginDrag(offset: { x: number; y: number }): void;
  /** Releases the drag, optionally handing over a velocity (px/s) for the host to glide out. */
  endDrag(velocity?: { x: number; y: number }): void;
  /** Grows or shrinks the window on one side without moving the body. */
  setExtension(extension: SurfaceExtension): void;
  setClickThrough(clickThrough: boolean): void;
  /** Subscribes to placement updates; returns an unsubscribe function. */
  onPlacement(listener: (placement: SurfacePlacement) => void): () => void;
  /** Subscribes to transient one-shot payloads relayed to this surface (background `surfaces.post`). */
  onMessage(listener: (payload: unknown) => void): () => void;
  /** Subscribes to retained state (background `surfaces.setState`), which the host replays after `ready()`. */
  onState(listener: (state: unknown) => void): () => void;
  /**
   * Announces that this component has installed its listeners, so the host
   * replays the retained state and the current placement. A surface that never
   * calls this comes up blank whenever it mounts after its state was set.
   */
  ready(): void;
  /** Opens a native context menu over this surface; resolves the chosen id, or null. */
  showContextMenu(items: SurfaceMenuItem[]): Promise<string | null>;
  /** Brings the main application window forward. */
  activateMainWindow(): void;
};

/** Props a plugin-authored `desktop.surface` component receives. */
export type PluginSurfaceComponentProps = {
  surfaceId: string;
  surface: SurfaceHandle;
  client: PluginRpcClient;
};
