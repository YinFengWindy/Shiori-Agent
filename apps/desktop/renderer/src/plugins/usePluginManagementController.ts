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
  const [trustCandidate, setTrustCandidate] = useState<PluginSummary | null>(null);
  const client = useMemo(() => createPluginBridgeClient(), []);

  const reload = useCallback(async () => {
    try {
      const list = await refreshPluginEnabledState(client);
      setPlugins(list);
      setError("");
      return true;
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      return false;
    }
  }, [client]);

  useEffect(() => { void reload(); }, [reload]);

  const runMutation = useCallback(async (pluginId: string, action: () => Promise<unknown>) => {
    setPendingIds((current) => new Set(current).add(pluginId));
    try {
      await action();
      return await reload();
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : String(toggleError));
      return false;
    } finally {
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(pluginId);
        return next;
      });
    }
  }, [reload]);

  const setEnabled = useCallback((pluginId: string, enabled: boolean) => runMutation(pluginId, () => client.setEnabled(pluginId, enabled, { operationId: crypto.randomUUID() })), [client, runMutation]);

  const confirmTrust = useCallback(async () => {
    if (!trustCandidate?.trustFingerprint) return;
    const candidate = trustCandidate;
    if (await runMutation(candidate.id, () => client.trustPlugin(candidate.candidateId, candidate.trustFingerprint!))) setTrustCandidate(null);
  }, [client, runMutation, trustCandidate]);

  const requestTrust = useCallback((candidate: PluginSummary) => {
    setError("");
    setTrustCandidate(candidate);
  }, []);

  return { plugins, error, pendingIds, setEnabled, reload, trustCandidate, requestTrust, confirmTrust, closeTrust: () => setTrustCandidate(null) };
}
