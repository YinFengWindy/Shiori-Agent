import { createElement, lazy } from "react";

/**
 * The schema form loads on first use. Besides keeping it out of the startup
 * bundle path, this keeps the plugin enabled-state store (which auto-registers
 * these pages) free of a static dependency on form controls: Base UI picks
 * DOM-dependent implementations when its modules are first evaluated.
 */
const LazyPluginSchemaSettingsSection = lazy(() => import("./PluginSchemaSettingsSection")
  .then((module) => ({ default: module.PluginSchemaSettingsSection })));

/** Binds a plugin id into a settings.subsection-compatible component (registry entry shape). */
export function createPluginSchemaSettingsSection(pluginId: string) {
  return function BoundPluginSchemaSettingsSection() {
    return createElement(LazyPluginSchemaSettingsSection, { pluginId });
  };
}
