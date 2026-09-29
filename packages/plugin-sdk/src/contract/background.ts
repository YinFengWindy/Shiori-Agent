/**
 * The `app.background` contribution contract: what a plugin's
 * `background/index.ts` default-exports and the `ctx` its `setup` receives.
 * React- and DOM-free.
 */
import type { BridgeEvent, PluginRpcClient } from "../rpc";
import type {
  SurfaceCreateResult,
  SurfacePlacement,
  SurfaceSettleReason,
  SurfaceSpec,
  SurfaceWorkArea,
} from "./surface";

/** What a background module is told when one of its surfaces comes to rest. */
export type PluginBackgroundSettled = {
  placement: SurfacePlacement;
  reason: SurfaceSettleReason;
  displayId: string;
};

/**
 * The plugin's own view of the DesktopSurface capability, pre-bound to its
 * plugin id, so a background module never passes its own id around by hand.
 */
export type PluginBackgroundSurfaces = {
  create(
    surfaceId: string,
    spec: SurfaceSpec,
    anchor: { x: number; y: number },
  ): Promise<SurfaceCreateResult>;
  destroy(surfaceId: string): Promise<void>;
  show(surfaceId: string): void;
  hide(surfaceId: string): void;
  workArea(surfaceId: string): Promise<SurfaceWorkArea>;
  setPosition(surfaceId: string, position: { x: number; y: number }): void;
  moveTo(surfaceId: string, position: { x: number; y: number }, durationMs: number): void;
  /** Relays a transient payload to the surface component, delivered on its `onMessage`. */
  post(surfaceId: string, message: unknown): void;
  /**
   * Sets the surface's retained state, replayed whenever its component reports
   * ready. Use this for anything the surface must still be showing after a
   * reload; use `post` for one-shot events.
   */
  setState(surfaceId: string, state: unknown): void;
  /**
   * Reports where one of this plugin's own surfaces came to rest.
   *
   * Filtered to the calling plugin and the named surface, and — like
   * `events.on` — the unsubscribe is registered by the host rather than handed
   * back, so it cannot be forgotten and is always released before `ctx.effect`
   * entries (#227).
   *
   * A surface moves under the host's control (drag, glide, eased move), so a
   * background module cannot know where its window ended up by watching its
   * own calls. `reason` is what separates "the user moved it" from "a panel
   * grew and the body stayed put".
   */
  onSettled(surfaceId: string, handler: (settled: PluginBackgroundSettled) => void): void;
};

/**
 * Persisted JSON private to one plugin, pre-bound to its id: state that must
 * outlive a restart but does not belong in the user-editable config form.
 *
 * `read` resolves `null` for a plugin that has never written, and also for a
 * file the host could not parse: either way the plugin's own defaults are the
 * only sensible answer.
 */
export type PluginBackgroundStore = {
  read(): Promise<unknown>;
  write(value: unknown): Promise<void>;
};

/**
 * One tray menu item owned by this plugin. `setEntry` is create-or-update so a
 * plugin can rewrite its own label without the item moving in the menu. Every
 * entry is reclaimed by the host when the plugin is disabled.
 */
export type PluginBackgroundTray = {
  setEntry(entryId: string, entry: { label: string; enabled?: boolean; onClick: () => void }): void;
  removeEntry(entryId: string): void;
};

/** Resolves trusted local paths a plugin received from its own backend. */
export type PluginBackgroundAssets = {
  /**
   * Turns an absolute path the host already granted into a displayable URL,
   * or `null` when it granted no such path (missing, unreadable or not a media
   * type the host serves) — which a plugin must handle as "cannot show this".
   */
  url(path: string): string | null;
};

/** Host event subscriptions are explicit and exclude plugin namespaces. */
export type PluginBackgroundEvents = {
  /** The envelope preserves producer identity for consumers of incremental events. */
  on(method: string, handler: (payload: Record<string, unknown>, event: BridgeEvent) => void): void;
};

/** Undoes one registered side effect. */
export type BackgroundEffectDispose = () => void | Promise<void>;

/**
 * The handle a plugin's `background/index.ts` receives in `setup(ctx)`.
 *
 * Deliberately narrow: there is no access to the main window's DOM or React
 * state, and no general-purpose IPC, so everything a background module can
 * reach is listed here. A capability lands when a real plugin needs it.
 */
export type BackgroundCtx = {
  surfaces: PluginBackgroundSurfaces;
  rpc: PluginRpcClient;
  events: PluginRpcClient["events"];
  hostEvents: PluginBackgroundEvents;
  store: PluginBackgroundStore;
  assets: PluginBackgroundAssets;
  tray: PluginBackgroundTray;
  /**
   * Registers a disposable side effect (a controller's `terminate()`, a
   * timer, a connection). Always disposed *after* every `events.on`
   * subscription has been unsubscribed.
   */
  effect(label: string, dispose: BackgroundEffectDispose): void;
  /**
   * Reports a failure the plugin handled but a human should still see
   * (runtime API 2.11.0): a fire-and-forget operation with no caller to throw
   * at, or a step `setup` deliberately survives. The background window is
   * hidden and its console is out of reach, so the host records the failure in
   * its desktop diagnostic log, prefixed with this plugin's id.
   */
  reportFailure(operation: string, error: unknown): void;
};

/** What a plugin's `background/index.ts` default-exports: its always-resident setup function. */
export type PluginBackgroundContribution = {
  pluginId: string;
  setup(ctx: BackgroundCtx): void | Promise<void>;
};
