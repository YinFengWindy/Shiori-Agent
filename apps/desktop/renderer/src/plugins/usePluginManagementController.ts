import { useCallback, useEffect, useMemo, useState } from "react";
import { createPluginBridgeClient, type PluginSummary } from "./pluginBridgeClient";
import { refreshPluginEnabledState } from "./pluginEnabledStateStore";

/**
 * Loads the plugin roster and lets the caller hot toggle one plugin at a
 * time. Also seeds the shared `pluginEnabledStateStore` from every load and
 * toggle, so the nav rail and settings sidebar (which read that store, not
 * this hook) hide a disabled plugin's UI entries immediately.
 */
export function usePluginManagementController() {
  const [plugins, setPlugins] = useState<PluginSummary[] | null>(null);
  const [error, setError] = useState("");
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const client = useMemo(() => createPluginBridgeClient(), []);

  const reload = useCallback(async () => {
    try {
      const list = await refreshPluginEnabledState(client);
      setPlugins(list);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    }
  }, [client]);

  useEffect(() => { void reload(); }, [reload]);

  const setEnabled = useCallback(async (pluginId: string, enabled: boolean) => {
    setPendingIds((current) => new Set(current).add(pluginId));
    try {
      await client.setEnabled(pluginId, enabled, { operationId: crypto.randomUUID() });
      await reload();
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : String(toggleError));
    } finally {
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(pluginId);
        return next;
      });
    }
  }, [client, reload]);

  return { plugins, error, pendingIds, setEnabled, reload };
}
