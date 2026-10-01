import type { PluginConfigValues } from "@shiori/sdk";

/** Receives a plugin's stored config after a save, with the writer that saved it. */
export type PluginConfigChangeListener = (values: PluginConfigValues, origin: object) => void;

/**
 * The host's single channel for "this plugin's config was just saved" (#505).
 * Every renderer writer of plugin config — the settings page controller and
 * each plugin's `host.config` — publishes its stored result here, so the
 * others refresh: the settings page reloads after a plugin saves, and a
 * plugin's `host.config.subscribe` hears saves from the settings page.
 * `origin` identifies the writer, so a writer can skip its own saves.
 */
export function createPluginConfigChanges() {
  const listeners = new Map<string, Set<PluginConfigChangeListener>>();
  return {
    publish(pluginId: string, values: PluginConfigValues, origin: object) {
      for (const listener of [...listeners.get(pluginId) ?? []]) listener({ ...values }, origin);
    },
    subscribe(pluginId: string, listener: PluginConfigChangeListener) {
      const forPlugin = listeners.get(pluginId) ?? new Set();
      listeners.set(pluginId, forPlugin);
      forPlugin.add(listener);
      return () => {
        forPlugin.delete(listener);
        if (!forPlugin.size) listeners.delete(pluginId);
      };
    },
  };
}

/** The channel type. */
export type PluginConfigChanges = ReturnType<typeof createPluginConfigChanges>;

/** The renderer's one channel, shared by the settings page and every plugin's `host.config`. */
export const pluginConfigChanges = createPluginConfigChanges();
