import {
  pluginSurfaceRegistry,
  type PluginSurfaceContribution,
  type PluginSurfaceRegistry,
} from "./pluginSurfaceRegistry";

/**
 * The shape a plugin's `surface/index.tsx` default-exports to own a desktop
 * window. A plugin id is required: it scopes the plugin's RPC namespace and is
 * how the host tells one surface window from another.
 */
export type PluginSurfaceModule = {
  pluginId: string;
  surface: PluginSurfaceContribution;
};

/**
 * Narrows an unknown default export without an unsafe cast. Exported so
 * `runtimePluginSurface.ts` can apply the identical structural check to a
 * runtime-loaded module, not a second hand-rolled copy of it.
 */
export function isPluginSurfaceModule(value: unknown): value is PluginSurfaceModule {
  if (value === null || typeof value !== "object") return false;
  if (!("pluginId" in value) || typeof value.pluginId !== "string" || !value.pluginId) return false;
  if (!("surface" in value) || value.surface === null || typeof value.surface !== "object") return false;
  return typeof (value.surface as { component?: unknown }).component === "function";
}

/**
 * Registers every plugin surface module found by the build-time glob.
 *
 * Pure and DOM-free (it only mutates the registry it is handed) so it is unit
 * testable against a hand-built module record, which is the only way to
 * exercise it — `import.meta.glob` results can only be produced by Vite. See
 * `pluginSurfaceModules.ts`.
 */
export function applyPluginSurfaceModules(
  modules: Record<string, { default: PluginSurfaceModule }>,
  registry: PluginSurfaceRegistry = pluginSurfaceRegistry,
): void {
  for (const [path, mod] of Object.entries(modules)) {
    const surfaceModule = mod.default;
    if (!isPluginSurfaceModule(surfaceModule)) {
      console.error(`[pluginSurfaceModules] ${path} 的默认导出不是合法的 PluginSurfaceModule，已跳过`);
      continue;
    }
    registry.register({
      slot: "desktop.surface",
      pluginId: surfaceModule.pluginId,
      Component: surfaceModule.surface.component,
    });
  }
}
