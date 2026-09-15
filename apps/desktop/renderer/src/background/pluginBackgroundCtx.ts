import type {
  BridgeEvent,
  DesktopApi,
  DesktopSurfacesApi,
  SurfaceSettledPayload,
} from "../../../src/bridge/shared";
import { unavailableLocalAssetUrl } from "../../../src/assets/localAssetContract";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { createPluginRpcClient } from "../plugins/pluginBridgeClient";
import type { BackgroundEffectScope } from "./backgroundEffectScope";
import type {
  BackgroundCtx,
  PluginBackgroundAssets,
  PluginBackgroundStore,
  PluginBackgroundSurfaces,
  PluginBackgroundTray,
} from "./pluginBackgroundRegistry";

/** Subscribes to every tray click this window is told about. */
export type TrayClickSource = (
  listener: (payload: { pluginId: string; entryId: string }) => void,
) => () => void;

/** The host tray API, before it is bound to one plugin. */
export type TrayApi = DesktopApi["tray"];

/** Subscribes to every surface settle this window is told about. */
export type SurfaceSettledSource = (
  listener: (settled: SurfaceSettledPayload) => void,
) => () => void;

/** Binds the shared `surfaces` bridge API to one plugin id, dropping it from every call. */
function createPluginBackgroundSurfaces(
  pluginId: string,
  api: DesktopSurfacesApi,
  onSurfaceSettled: SurfaceSettledSource,
  scope: BackgroundEffectScope,
): PluginBackgroundSurfaces {
  return {
    create: (surfaceId, spec, anchor) => api.create(pluginId, surfaceId, spec, anchor),
    destroy: (surfaceId) => api.destroy(pluginId, surfaceId),
    show: (surfaceId) => api.show(pluginId, surfaceId),
    hide: (surfaceId) => api.hide(pluginId, surfaceId),
    workArea: (surfaceId) => api.workArea(pluginId, surfaceId),
    setPosition: (surfaceId, position) => api.setPosition(pluginId, surfaceId, position),
    moveTo: (surfaceId, position, durationMs) => api.moveTo(pluginId, surfaceId, position, durationMs),
    post: (surfaceId, message) => api.post(pluginId, surfaceId, message),
    setState: (surfaceId, state) => api.setState(pluginId, surfaceId, state),
    onSettled(surfaceId, handler) {
      const unsubscribe = onSurfaceSettled((settled) => {
        if (settled.pluginId !== pluginId || settled.surfaceId !== surfaceId) return;
        handler({
          placement: settled.placement,
          reason: settled.reason,
          displayId: settled.displayId,
        });
      });
      // Event phase, exactly like `events.on`: a settle arriving while a
      // plugin's `ctx.effect` teardown is running would hand it work nothing
      // is left to undo. See `BackgroundEffectScope` (#227).
      scope.addEventEffect(`surface-settled:${surfaceId}`, unsubscribe);
    },
  };
}

/** Binds the host's plugin data store to one plugin id. */
function createPluginBackgroundStore(
  pluginId: string,
  pluginData: DesktopApi["pluginData"],
): PluginBackgroundStore {
  return {
    read: () => pluginData.read(pluginId),
    write: (value) => pluginData.write(pluginId, value),
  };
}

/** Maps the preload's "no grant" sentinel onto `null` for plugin code. */
function createPluginBackgroundAssets(localAssetUrl: (path: string) => string): PluginBackgroundAssets {
  return {
    url(path) {
      if (!path) return null;
      const url = localAssetUrl(path);
      // The preload answers an ungranted path with a fixed placeholder URL
      // rather than throwing. That is right for an `<img src>`, which needs
      // *something*, but wrong for a plugin deciding whether it can show a
      // package at all — so the sentinel becomes `null` here, at the one place
      // that knows what it means.
      return url && url !== unavailableLocalAssetUrl ? url : null;
    },
  };
}

/**
 * Binds the host tray to one plugin id, and owns reclaiming its entries.
 *
 * Two different disposal phases are in play and the difference matters (#227):
 * the click subscription is an *event* effect, so it is cut before anything
 * else on teardown — a click arriving mid-teardown must not reach a plugin that
 * is being disposed. Removing the entries themselves is an ordinary effect, so
 * it runs after. Both are registered on the first `setEntry`, once, however
 * many entries the plugin goes on to contribute or how often it rewrites them.
 */
function createPluginBackgroundTray(
  pluginId: string,
  tray: TrayApi,
  onTrayEntryClicked: TrayClickSource,
  scope: BackgroundEffectScope,
): PluginBackgroundTray {
  const handlers = new Map<string, () => void>();
  let registered = false;
  let disposed = false;

  const register = () => {
    if (registered) return;
    registered = true;
    const unsubscribe = onTrayEntryClicked((payload) => {
      if (payload.pluginId !== pluginId) return;
      handlers.get(payload.entryId)?.();
    });
    scope.addEventEffect("tray:clicks", unsubscribe);
    // One host-side call rather than replaying `removeEntry` per id: the host
    // owns the menu, so this reclaims everything the plugin contributed even if
    // this side's bookkeeping has drifted — and the host can make the same call
    // itself when a plugin's renderer dies without running any teardown.
    scope.addEffect("tray:entries", () => {
      disposed = true;
      handlers.clear();
      tray.removeAllEntries(pluginId);
    });
  };

  return {
    setEntry(entryId, entry) {
      // Silently ignored after teardown rather than trusted not to happen. A
      // plugin can have an `await` in flight across being disabled — the pet
      // persists its position outside its own operation queue, so a store
      // write can return after `disposeAll()` and drive one more `setEntry`.
      // Without this the entry is written straight back into the host's
      // registry, with its click subscription already cut: a menu item that
      // outlives its plugin and does nothing when clicked, until the next
      // launch. Keeping the invariant inside the capability means no plugin
      // has to be careful for it to hold.
      if (disposed) return;
      register();
      handlers.set(entryId, entry.onClick);
      tray.setEntry(pluginId, entryId, { label: entry.label, enabled: entry.enabled });
    },
    removeEntry(entryId) {
      if (disposed) return;
      handlers.delete(entryId);
      tray.removeEntry(pluginId, entryId);
    },
  };
}

/**
 * Builds the `ctx` handed to one plugin's `background/index.ts` `setup(ctx)`.
 *
 * `onEvent` is the raw, unfiltered `desktop:event` stream (see
 * `apps/desktop/src/bridge/bridgeLifecycle.ts::wireBridgeEvents`, which
 * broadcasts to every open renderer window, including this hidden one).
 * `ctx.events.on` filters it to one `method` and — this is the part that
 * matters for #227 — registers its own unsubscribe into `scope`'s
 * event phase rather than handing the caller an unsubscribe function to
 * manage itself, so a plugin cannot forget to release it, and it is always
 * released before `ctx.effect` entries regardless of call order.
 * `ctx.surfaces.onSettled` follows the same rule for the same reason.
 */
export function createBackgroundCtx(options: {
  pluginId: string;
  surfaces: DesktopSurfacesApi;
  invoke: DesktopInvoke;
  onEvent: (listener: (event: BridgeEvent) => void) => () => void;
  onSurfaceSettled: SurfaceSettledSource;
  pluginData: DesktopApi["pluginData"];
  tray: TrayApi;
  onTrayEntryClicked: TrayClickSource;
  localAssetUrl: (path: string) => string;
  scope: BackgroundEffectScope;
}): BackgroundCtx {
  const {
    pluginId, surfaces, invoke, onEvent, onSurfaceSettled,
    pluginData, tray, onTrayEntryClicked, localAssetUrl, scope,
  } = options;
  return {
    surfaces: createPluginBackgroundSurfaces(pluginId, surfaces, onSurfaceSettled, scope),
    rpc: createPluginRpcClient(pluginId, invoke),
    events: {
      on(method, handler) {
        const unsubscribe = onEvent((event) => {
          if (event.method === method) handler(event.payload, event);
        });
        scope.addEventEffect(`event:${method}`, unsubscribe);
      },
    },
    store: createPluginBackgroundStore(pluginId, pluginData),
    assets: createPluginBackgroundAssets(localAssetUrl),
    tray: createPluginBackgroundTray(pluginId, tray, onTrayEntryClicked, scope),
    effect(label, dispose) {
      scope.addEffect(label, dispose);
    },
  };
}
