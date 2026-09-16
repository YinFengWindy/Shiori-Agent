import { pluginRuntimeChanged } from "../plugins/pluginRuntimeChanged";
// Registers every plugin's `background/index.ts` before the host reads the registry.
import "./pluginBackgroundModules";
import { createPluginBridgeClient } from "../plugins/pluginBridgeClient";
import { activePluginIds } from "../plugins/activePluginIds";
import { reportBackgroundFailure } from "./backgroundDiagnostics";
import { createBackgroundCtx } from "./pluginBackgroundCtx";
import { PluginBackgroundHost } from "./pluginBackgroundHost";
import { pluginBackgroundRegistry } from "./pluginBackgroundRegistry";

/**
 * Entry point for `plugin-host.html`: the dedicated hidden renderer window
 * (#226 item 1) that owns every plugin's always-resident `app.background`
 * contribution. See `apps/desktop/src/pluginHost/window.ts` for why this runs
 * in its own window rather than the main window's renderer.
 *
 * There is no DOM to mount here — a background module is a controller, not a
 * component — so unlike `surface/main.tsx` this file wires plain objects, not
 * React.
 */
const invoke = window.miraDesktop.invoke;
const onEvent = window.miraDesktop.onEvent;
const pluginBridge = createPluginBridgeClient(invoke);

const host = new PluginBackgroundHost({
  registry: pluginBackgroundRegistry,
  async listEnabledPluginIds() {
    const plugins = await pluginBridge.listPlugins();
    return activePluginIds(plugins);
  },
  subscribeRosterChanged(listener) {
    // `runtime.applied` is the roster-changed signal — but note *where* it is
    // published from. The backend emits it explicitly, per request branch, in
    // `desktop_bridge/runtime/service.py`. `RuntimeSettingsApplication.apply()`
    // itself publishes nothing; its `publish_service(service)` call only swaps
    // the service generation. `plugins.setEnabled` reached no publish at all
    // until #226 added one to the PLUGIN_MANAGEMENT branch — before that, this
    // window never learned a plugin had been disabled and kept its background
    // contribution running. **Do not delete that publish as redundant**: it is
    // the only thing making disable-means-disable true here, and
    // `test_set_enabled_publishes_runtime_applied` pins it.
    return onEvent((event) => {
      if (pluginRuntimeChanged(event)) listener(event.method !== "bridge.exit");
    });
  },
  createCtx(pluginId, scope) {
    return createBackgroundCtx({
      pluginId,
      surfaces: window.miraDesktop.surfaces,
      invoke,
      onEvent,
      onSurfaceSettled: window.miraDesktop.onSurfaceSettled,
      pluginData: window.miraDesktop.pluginData,
      tray: window.miraDesktop.tray,
      onTrayEntryClicked: window.miraDesktop.tray.onEntryClicked,
      localAssetUrl: (path) => window.miraDesktop.localAssetUrl(path),
      scope,
    });
  },
  onError(pluginId, phase, error) {
    const what = phase === "roster" ? "读取插件启用名单" : pluginId + " 的 " + (phase === "setup" ? "setup" : "卸载");
    reportBackgroundFailure(what, error);
  },
});

void host.start();
