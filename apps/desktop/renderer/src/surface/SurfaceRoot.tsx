import type { ComponentType } from "react";
import { usePluginRpcClient } from "../plugins/usePluginRpcClient";
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
  type PluginSurfaceComponentProps,
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
      <BoundSurface
        Component={Component}
        pluginId={key.pluginId}
        surfaceId={key.surfaceId}
        surface={props.surface}
      />
    </SurfaceErrorBoundary>
  );
}

function BoundSurface({ pluginId, Component, ...props }: Omit<PluginSurfaceComponentProps, "client"> & { pluginId: string; Component: ComponentType<PluginSurfaceComponentProps> }) {
  const client = usePluginRpcClient(pluginId);
  return <Component {...props} client={client} />;
}
