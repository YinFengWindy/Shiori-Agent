/**
 * The `desktop.surface` contribution: what a plugin's `surface/index.tsx`
 * default-exports. Kept apart from `./surface` because it names a React
 * component type, which the main-process view (`/contract`) cannot load.
 */
import type React from "react";
import type { PluginSurfaceComponentProps } from "./surface";

/** One plugin's `desktop.surface` contribution. */
export type PluginSurfaceContribution = {
  component: React.ComponentType<PluginSurfaceComponentProps>;
};

/**
 * The shape a plugin's `surface/index.tsx` default-exports to own a desktop
 * window. The plugin id scopes its RPC namespace and is how the host tells one
 * surface window from another.
 */
export type PluginSurfaceModule = {
  pluginId: string;
  surface: PluginSurfaceContribution;
};
