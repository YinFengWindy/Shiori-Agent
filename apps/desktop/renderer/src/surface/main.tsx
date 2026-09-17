import { createRoot } from "react-dom/client";
import { SurfaceRoot } from "./SurfaceRoot";
import { SurfaceFailure } from "./SurfaceFailure";
import { surfaceKeyFromSearch } from "../../../src/surface/entry";
import { createPluginBridgeClient } from "../plugins/pluginBridgeClient";
import { importRuntimePluginModule, loadRuntimePluginCss } from "../plugins/runtimePluginDomLoader";
import { loadRuntimePluginSurface } from "./runtimePluginSurface";
import { bootstrapSurfaceWindow } from "./surfaceBootstrap";
import "../styles.css";

const root = createRoot(document.getElementById("root") as HTMLElement);
const surface = window.miraDesktop.surface;
const key = surfaceKeyFromSearch(window.location.search);

/**
 * Loads this window's own plugin's runtime `renderer.surface` entry
 * (#213/#262), if the roster admitted one. A no-op for a built-in plugin
 * (whose surface is already registered by the build-time glob) and for a
 * plugin that declared no `surface` at all; a failure is reported through the
 * renderer diagnostic path and simply leaves `SurfaceRoot` to render its
 * existing "this plugin registered nothing" card below.
 */
async function loadOwnRuntimeSurface() {
  if (!key) return;
  const pluginBridge = createPluginBridgeClient();
  const plugins = await pluginBridge.listPlugins();
  const entry = plugins.find((plugin) => plugin.id === key.pluginId)?.rendererSurface;
  if (!entry) return;
  await loadRuntimePluginSurface(entry, {
    importModule: importRuntimePluginModule,
    loadCss: loadRuntimePluginCss,
    failed: (pluginId, error) => {
      console.error(`[surface] ${pluginId}`, error);
      const message = error instanceof Error ? error.message : String(error);
      window.miraDesktop.reportRendererDiagnostic({
        kind: "error",
        message,
        details: { pluginId, event: "plugin-surface.load.failed", state: "FAILED", stage: "renderer" },
      });
      // A surface is not part of the initial activation gate (#262 kernel.py
      // `_RENDERER_GATED_KINDS`), but its failure must still roll the whole
      // plugin back — tools/RPC/UI/background must not outlive a surface
      // that could not load (#262 AC2).
      void pluginBridge.reportActivation(pluginId, "surface", { ok: false, reason: message }).catch(() => undefined);
    },
  });
}

// Assembly only — the actual branching (glob failure vs. runtime failure vs.
// success) lives in the injected-dependency, unit-tested `surfaceBootstrap.ts`.
void bootstrapSurfaceWindow({
  // Isolated from the runtime step below: a bad build-time module must not
  // prevent the host's failure card from mounting and reporting ready.
  loadGlobModules: () => import("./pluginSurfaceModules"),
  // This step talks to the bridge (`plugins.list`), so it can reject for
  // reasons that have nothing to do with the plugin — a bridge that is not
  // up yet, an RPC error. `bootstrapSurfaceWindow` still renders afterwards:
  // since #222 a surface window stays `show: false` until its content
  // reports ready, so skipping the render would leave the window permanently
  // hidden with no explanation. Per-entry module failures are already
  // handled inside `loadOwnRuntimeSurface` itself.
  loadOwnRuntimeSurface,
  renderFailure: (detail) => root.render(<SurfaceFailure detail={detail} surface={surface} />),
  renderSurface: () => root.render(<SurfaceRoot search={window.location.search} surface={surface} />),
  onError: (scope, error) => console.error(
    scope === "glob" ? "[surface] 插件模块加载失败" : "[surface] 运行时 surface 入口加载失败",
    error,
  ),
});
