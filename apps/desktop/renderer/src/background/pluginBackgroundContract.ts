import {
  pluginBackgroundRegistry,
  type BackgroundCtx,
  type PluginBackgroundRegistry,
} from "./pluginBackgroundRegistry";

/**
 * The shape a plugin's `background/index.ts` default-exports to own an
 * always-resident `app.background` contribution.
 *
 * This lives in its own `background/` directory, deliberately separate from
 * `ui/` and `surface/` — same reasoning `pluginSurfaceRegistry.ts` documents
 * for not reusing `pluginUiRegistry`: hanging this off `ui/index.tsx` would
 * pull the whole settings/nav UI module graph into the `plugin-host.html`
 * bundle, which has no DOM to render any of it into.
 */
export type PluginBackgroundContribution = {
  pluginId: string;
  setup(ctx: BackgroundCtx): void | Promise<void>;
};

/**
 * Narrows an unknown default export down to a well-formed
 * PluginBackgroundContribution. Exported so `runtimePluginBackground.ts` can
 * apply the identical structural check to a runtime-loaded module, not a
 * second hand-rolled copy of it.
 */
export function isPluginBackgroundModule(value: unknown): value is PluginBackgroundContribution {
  if (value === null || typeof value !== "object") return false;
  if (!("pluginId" in value) || typeof value.pluginId !== "string" || !value.pluginId) return false;
  return typeof (value as { setup?: unknown }).setup === "function";
}

/**
 * Registers every plugin background module found by the build-time glob.
 *
 * Pure and DOM-free (it only mutates the registry it is handed) so it is unit
 * testable against a hand-built module record, which is the only way to
 * exercise it — `import.meta.glob` results can only be produced by Vite. See
 * `pluginBackgroundModules.ts`.
 */
export function applyPluginBackgroundModules(
  modules: Record<string, { default: PluginBackgroundContribution }>,
  registry: PluginBackgroundRegistry = pluginBackgroundRegistry,
): void {
  for (const [path, mod] of Object.entries(modules)) {
    const backgroundModule = mod.default;
    if (!isPluginBackgroundModule(backgroundModule)) {
      console.error(`[pluginBackgroundModules] ${path} 的默认导出不是合法的 PluginBackgroundContribution，已跳过`);
      continue;
    }
    registry.register({
      slot: "app.background",
      pluginId: backgroundModule.pluginId,
      setup: backgroundModule.setup,
    });
  }
}
