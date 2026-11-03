import type { PluginFrontendModule } from "@yinfengwindy/shiori-sdk";
import type { PluginSurfaceModule } from "@yinfengwindy/shiori-sdk";
import { pluginSurfaceRegistry, type PluginSurfaceRegistry } from "./pluginSurfaceRegistry";

/**
 * Narrows an unknown named export without an unsafe cast. Exported so
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
 * Registers every plugin surface module found by the frontend inventory.
 *
 * Pure and DOM-free (it only mutates the registry it is handed) so it is unit
 * testable against a hand-built module record, which is the only way to
 * exercise it — `import.meta.glob` results can only be produced by Vite. See
 * `pluginSurfaceModules.ts`.
 */
export function applyPluginSurfaceModules(
  modules: Record<string, PluginFrontendModule>,
  registry: PluginSurfaceRegistry = pluginSurfaceRegistry,
): void {
  for (const [path, mod] of Object.entries(modules)) {
    const surfaceModule = mod.surface;
    if (mod.surface === undefined) continue;
    if (!isPluginSurfaceModule(surfaceModule)) {
      console.error(`[pluginSurfaceModules] ${path} 的surface 导出不是合法的 PluginSurfaceModule，已跳过`);
      continue;
    }
    registry.register({
      slot: "desktop.surface",
      pluginId: surfaceModule.pluginId,
      Component: surfaceModule.surface.component,
    });
  }
}
