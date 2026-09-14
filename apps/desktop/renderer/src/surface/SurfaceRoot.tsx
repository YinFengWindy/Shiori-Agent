import { createPluginRpcClient } from "../plugins/pluginBridgeClient";
import { SurfaceFailure } from "./SurfaceFailure";
import { SurfaceErrorBoundary } from "./SurfaceErrorBoundary";
// The main process builds this query string; sharing the parser keeps the two
// sides from drifting. `entry.ts` only imports a *type* from `host.ts`, so
// nothing main-process-only is pulled into the surface bundle.
import { surfaceKeyFromSearch } from "../../../src/surface/entry";
import {
  pluginSurfaceRegistry,
  type PluginSurfaceRegistry,
  type SurfaceHandle,
} from "./pluginSurfaceRegistry";

/**
 * Mounts whichever plugin owns this surface window.
 *
 * A surface window is transparent and always on top, so a failure here would
 * otherwise be *invisible* — an empty rectangle floating over the desktop with
 * nothing to click and no error anywhere the user can reach. Every failure
 * path below therefore renders something readable and logs, rather than
 * returning null.
 */
export function SurfaceRoot(props: {
  search: string;
  surface: SurfaceHandle;
  registry?: PluginSurfaceRegistry;
}) {
  const key = surfaceKeyFromSearch(props.search);
  if (!key) {
    return <SurfaceFailure detail="窗口参数缺失" surface={props.surface} />;
  }
  const entry = (props.registry ?? pluginSurfaceRegistry).get(key.pluginId);
  if (!entry) {
    return <SurfaceFailure detail={`插件 ${key.pluginId} 未提供桌面窗口`} surface={props.surface} />;
  }
  const Component = entry.Component;
  return (
    <SurfaceErrorBoundary key={`${key.pluginId}/${key.surfaceId}`} surface={props.surface}>
      <Component
        surfaceId={key.surfaceId}
        surface={props.surface}
        client={createPluginRpcClient(key.pluginId)}
      />
    </SurfaceErrorBoundary>
  );
}
