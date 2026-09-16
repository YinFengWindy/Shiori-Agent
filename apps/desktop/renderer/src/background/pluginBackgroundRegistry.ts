import { PluginContributionRegistry } from "../plugins/pluginContributionRegistry";
import type { BackgroundEffectDispose } from "./backgroundEffectScope";
import type {
  BridgeEvent,
  SurfaceCreateResultPayload,
  SurfacePlacementPayload,
  SurfaceSettledPayload,
  SurfaceSpecPayload,
} from "../../../src/bridge/shared";
import type { PluginRpcClient } from "../plugins/pluginBridgeClient";

/** What a background module is told when one of its surfaces comes to rest. */
export type PluginBackgroundSettled = Omit<SurfaceSettledPayload, "pluginId" | "surfaceId">;

/**
 * The plugin's own view of the DesktopSurface capability, pre-bound to its
 * plugin id — the same treatment `createPluginRpcClient` gives `ctx.rpc`, so
 * a background module never passes its own id around by hand. Mirrors
 * `DesktopSurfacesApi` minus the leading `pluginId` argument, plus `onSettled`,
 * which has no `DesktopSurfacesApi` counterpart because it is a push, not a
 * call.
 */
export type PluginBackgroundSurfaces = {
  create(
    surfaceId: string,
    spec: SurfaceSpecPayload,
    anchor: { x: number; y: number },
  ): Promise<SurfaceCreateResultPayload>;
  destroy(surfaceId: string): Promise<void>;
  show(surfaceId: string): void;
  hide(surfaceId: string): void;
  workArea(surfaceId: string): Promise<SurfacePlacementPayload["workArea"]>;
  setPosition(surfaceId: string, position: { x: number; y: number }): void;
  moveTo(surfaceId: string, position: { x: number; y: number }, durationMs: number): void;
  post(surfaceId: string, message: unknown): void;
  setState(surfaceId: string, state: unknown): void;
  /**
   * Reports where one of this plugin's own surfaces came to rest.
   *
   * Filtered to the calling plugin and the named surface, and — like
   * `events.on` — the unsubscribe is registered into the scope's event phase
   * rather than handed back, so it cannot be forgotten and is always released
   * before `ctx.effect` entries (#227).
   *
   * A surface moves under the host's control (drag, glide, eased move), so a
   * background module cannot know where its window ended up by watching its
   * own calls. `reason` is what separates "the user moved it" from "a panel
   * grew and the body stayed put" — persisting on the latter would rewrite
   * stored state every time a bubble appeared.
   */
  onSettled(surfaceId: string, handler: (settled: PluginBackgroundSettled) => void): void;
};

/**
 * Persisted JSON private to one plugin, pre-bound to its id.
 *
 * Background code runs in a renderer with no filesystem, but plenty of plugins
 * have state that must outlive a restart and does not belong in the
 * user-editable config form (`plugin.config.*`) — the desktop pet's remembered
 * window position per role and display being the first case.
 *
 * `read` resolves `null` for a plugin that has never written, and also for a
 * file the host could not parse: either way the plugin's own defaults are the
 * only sensible answer, and making it distinguish the two would not change
 * what it does.
 */
export type PluginBackgroundStore = {
  read(): Promise<unknown>;
  write(value: unknown): Promise<void>;
};

/**
 * One tray menu item owned by this plugin.
 *
 * A `Tray` is main-process-only, so a plugin cannot build one; it says what its
 * item should read and is told when the user picks it. `setEntry` is
 * create-or-update so a plugin can rewrite its own label as its state changes
 * without the item moving in the menu.
 *
 * Every entry is reclaimed when the plugin is disabled, by the host rather than
 * by the plugin — that is what makes #181's "停用桌宠插件后...托盘...全部回收"
 * independent of disabled code getting a chance to run.
 */
export type PluginBackgroundTray = {
  setEntry(entryId: string, entry: { label: string; enabled?: boolean; onClick: () => void }): void;
  removeEntry(entryId: string): void;
};

/** Resolves trusted local paths a plugin received from its own backend. */
export type PluginBackgroundAssets = {
  /**
   * Turns an absolute path the host already granted into a displayable URL,
   * or `null` when it granted no such path.
   *
   * A grant is issued when a bridge response carries the path in one of the
   * declared asset fields (`apps/desktop/src/assets/localAssetPolicy.ts`), so
   * "not granted" means the file is missing, unreadable or not a media type
   * the host serves — all of which a plugin must handle as "cannot show this"
   * rather than by rendering a broken image.
   */
  url(path: string): string | null;
};

/** Host event subscriptions are explicit and exclude plugin namespaces. */
export type PluginBackgroundEvents = {
  /** The envelope preserves producer identity for consumers of incremental events. */
  on(method: string, handler: (payload: Record<string, unknown>, event: BridgeEvent) => void): void;
};

/**
 * The handle a plugin's `background/index.ts` receives in `setup(ctx)`.
 *
 * Deliberately narrow. There is no access to the main window's DOM or React
 * state, because this code may not even be running in the same renderer as the
 * main window — and no general-purpose IPC, so everything a background module
 * can reach is something listed here.
 *
 * `tray` arrived in #181-D with the desktop pet as its first consumer, which
 * is the order the rest of these were added in too: a capability lands when a
 * real plugin needs it, not ahead of one.
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
   * subscription has been unsubscribed — see `BackgroundEffectScope`.
   */
  effect(label: string, dispose: BackgroundEffectDispose): void;
};

/** One plugin's `app.background` contribution: its always-resident setup function. */
export type PluginBackgroundEntry = {
  slot: "app.background";
  pluginId: string;
  setup(ctx: BackgroundCtx): void | Promise<void>;
};

/**
 * Plugin-owned headless background contributions, kept in a registry of their
 * own rather than in `pluginUiRegistry` or `pluginSurfaceRegistry`.
 *
 * Same reasoning as `pluginSurfaceRegistry.ts`: this registry is loaded by the
 * `plugin-host.html` bundle, which must not carry the main window's settings
 * UI (`pluginUiRegistry`) or any surface component (`pluginSurfaceRegistry`) —
 * it has no DOM to render either of those into.
 */
export class PluginBackgroundRegistry extends PluginContributionRegistry<PluginBackgroundEntry> {
  constructor() {
    super("pluginBackgroundRegistry", "app.background");
  }
}

/** Process-wide background registry; populated at module load by `pluginBackgroundModules.ts`. */
export const pluginBackgroundRegistry = new PluginBackgroundRegistry();
