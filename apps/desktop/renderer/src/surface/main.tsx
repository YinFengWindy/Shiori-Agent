import { createRoot } from "react-dom/client";
import { SurfaceRoot } from "./SurfaceRoot";
import { SurfaceFailure } from "./SurfaceFailure";
import { surfaceKeyFromSearch } from "../../../src/surface/entry";
import { createPluginBridgeClient } from "../plugins/pluginBridgeClient";
import { importRuntimePluginModule, loadRuntimePluginCss } from "../plugins/runtimePluginDomLoader";
import { loadRuntimePluginSurface } from "./runtimePluginSurface";
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
  const plugins = await createPluginBridgeClient().listPlugins();
  const entry = plugins.find((plugin) => plugin.id === key.pluginId)?.rendererSurface;
  if (!entry) return;
  await loadRuntimePluginSurface(entry, {
    importModule: importRuntimePluginModule,
    loadCss: loadRuntimePluginCss,
    failed: (pluginId, error) => {
      console.error(`[surface] ${pluginId}`, error);
      window.miraDesktop.reportRendererDiagnostic({
        kind: "error",
        message: error instanceof Error ? error.message : String(error),
        details: { pluginId, event: "plugin-surface.load.failed", state: "FAILED", stage: "renderer" },
      });
    },
  });
}

async function bootstrap() {
  // Keep the existing build-time registry, but isolate its evaluation so a bad
  // module cannot prevent the host's failure card from mounting and reporting ready.
  try {
    await import("./pluginSurfaceModules");
  } catch (error) {
    console.error("[surface] 插件模块加载失败", error);
    root.render(<SurfaceFailure detail="插件模块加载失败" surface={surface} />);
    return;
  }
  // Same isolation as the glob import above, for the same reason. This step
  // talks to the bridge (`plugins.list`), so it can reject for reasons that
  // have nothing to do with the plugin — a bridge that is not up yet, an RPC
  // error. Letting that escape would skip the `root.render` below entirely,
  // and since #222 a surface window stays `show: false` until its content
  // reports ready: the user would get a window that never appears and never
  // explains why. Per-entry module failures are already handled inside
  // `loadOwnRuntimeSurface`; this catch is for everything around them.
  try {
    await loadOwnRuntimeSurface();
  } catch (error) {
    console.error("[surface] 运行时 surface 入口加载失败", error);
  }
  root.render(<SurfaceRoot search={window.location.search} surface={surface} />);
}

void bootstrap();
