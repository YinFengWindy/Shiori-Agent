import type { BackgroundCtx } from "@shiori/sdk";
import { PluginContributionRegistry } from "../plugins/pluginContributionRegistry";

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
