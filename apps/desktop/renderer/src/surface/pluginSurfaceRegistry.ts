import type React from "react";
import type { PluginSurfaceComponentProps } from "@shiori/sdk";
import { PluginContributionRegistry } from "../plugins/pluginContributionRegistry";

export type PluginSurfaceEntry = {
  slot: "desktop.surface";
  pluginId: string;
  Component: React.ComponentType<PluginSurfaceComponentProps>;
};

/**
 * Plugin-owned desktop surfaces, kept in a registry of their own rather than
 * in `pluginUiRegistry`.
 *
 * The two serve different bundles: `pluginUiRegistry` is loaded by the main
 * window and pulls in the whole settings UI with it, while this one is loaded
 * by `surface.html` — a transparent always-on-top window that should carry
 * only what it draws. Sharing one registry would drag the entire main-window
 * UI into every surface window's bundle.
 */
class PluginSurfaceRegistry extends PluginContributionRegistry<PluginSurfaceEntry> {
  constructor() {
    super("pluginSurfaceRegistry", "desktop.surface");
  }
}

/** Process-wide surface registry; populated at module load by `pluginSurfaceModules.ts`. */
export const pluginSurfaceRegistry = new PluginSurfaceRegistry();

/** Exposed for tests that need an isolated registry instead of the shared singleton. */
export { PluginSurfaceRegistry };
