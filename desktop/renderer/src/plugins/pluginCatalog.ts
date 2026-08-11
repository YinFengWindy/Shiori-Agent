import { useEffect, useMemo, useState } from "react";
import type { LoadedPluginManifest, PluginSettingField, PluginUiContribution, PluginUiSlot } from "../../../src/shared.js";

function isSettingField(value: unknown): value is PluginSettingField {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  const fieldTypes = ["boolean", "number", "secret", "select", "string"];
  const optionsValid = item.options === undefined || (
    Array.isArray(item.options)
    && item.options.every((option) => {
      if (!option || typeof option !== "object") return false;
      const entry = option as Record<string, unknown>;
      return typeof entry.label === "string"
        && (typeof entry.value === "string" || typeof entry.value === "number");
    })
  );
  return typeof item.id === "string"
    && typeof item.label === "string"
    && typeof item.type === "string"
    && fieldTypes.includes(item.type)
    && typeof item.config_path === "string"
    && optionsValid;
}

function isContribution(value: unknown): value is PluginUiContribution {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === "string"
    && typeof item.slot === "string"
    && typeof item.title === "string"
    && typeof item.renderer === "string"
    && typeof item.order === "number"
    && (item.settings_schema === undefined
      || (Array.isArray(item.settings_schema) && item.settings_schema.every(isSettingField)));
}

/** Returns the namespace-safe identity of one plugin contribution. */
export function pluginContributionKey(pluginId: string, contributionId: string) {
  return `${pluginId}:${contributionId}`;
}

function isManifest(value: unknown): value is LoadedPluginManifest {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.plugin_id === "string"
    && typeof item.name === "string"
    && Array.isArray(item.capabilities)
    && Array.isArray(item.rpc_methods)
    && Array.isArray(item.ui_contributions)
    && item.ui_contributions.every(isContribution);
}

/** Loads renderer-safe manifests whenever the desktop bridge becomes available. */
export function usePluginCatalog(bridgeState: string) {
  const [plugins, setPlugins] = useState<LoadedPluginManifest[]>([]);

  useEffect(() => {
    if (bridgeState !== "online") {
      setPlugins((current) => current.length ? [] : current);
      return;
    }
    let cancelled = false;
    void window.miraDesktop.invoke({ method: "plugins.list", payload: {} })
      .then((response) => {
        if (cancelled) return;
        if (response.error) {
          setPlugins([]);
          return;
        }
        const raw = response.payload.plugins;
        setPlugins(Array.isArray(raw) ? raw.filter(isManifest) : []);
      })
      .catch(() => {
        if (!cancelled) setPlugins([]);
      });
    return () => {
      cancelled = true;
    };
  }, [bridgeState]);

  return useMemo(() => createPluginCatalog(plugins), [plugins]);
}

export type PluginCatalog = {
  plugins: LoadedPluginManifest[];
  hasRenderer: (renderer: string) => boolean;
  contributions: (slot: PluginUiSlot) => Array<{
    plugin: LoadedPluginManifest;
    contribution: PluginUiContribution;
  }>;
};

/** Builds the stable catalog shape used by providers and focused tests. */
export function createPluginCatalog(plugins: LoadedPluginManifest[]): PluginCatalog {
  return {
    plugins,
    hasRenderer(renderer: string) {
      return plugins.some((plugin) => plugin.ui_contributions.some((contribution) => contribution.renderer === renderer));
    },
    contributions(slot: PluginUiSlot) {
      return plugins
        .flatMap((plugin) => plugin.ui_contributions.map((contribution) => ({ plugin, contribution })))
        .filter((item) => item.contribution.slot === slot)
        .sort((left, right) => left.contribution.order - right.contribution.order || left.contribution.id.localeCompare(right.contribution.id));
    },
  };
}
