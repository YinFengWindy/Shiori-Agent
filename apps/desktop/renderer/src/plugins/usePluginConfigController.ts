import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SerialDraftQueue, type DraftSavePhase } from "../shared/serialDraftQueue";
import { PluginBridgeError, createPluginBridgeClient, type PluginConfigSaveResult, type PluginConfigSnapshot } from "./pluginBridgeClient";
import { pluginConfigChanges } from "./pluginConfigChanges";

type PluginConfigValues = Record<string, unknown>;

// A validation rejection is the only failure the user can fix by editing
// further without reloading; anything else (TOML round-trip issues,
// unexpected backend errors) pauses until an explicit retry or reload.
const RECOVERABLE_WITHOUT_RELOAD = new Set(["plugin_config_invalid"]);

function cloneValues(values: PluginConfigValues): PluginConfigValues {
  return JSON.parse(JSON.stringify(values)) as PluginConfigValues;
}

function valuesEqual(a: PluginConfigValues | null, b: PluginConfigValues | null): boolean {
  if (!a || !b) return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Loads and autosaves one plugin's config through `plugin.config.get/set`.
 * Mirrors `useSettingsPageController`'s load/draft/autosave shape but stays
 * independent of it: plugin config lives in its own backend table with no
 * shared generation from `plugin.config.get`, so it does not participate
 * in the main settings draft's optimistic-concurrency tracking (a
 * concurrent save there and here that touch unrelated tables coexist
 * safely; see `desktop_bridge/runtime/plugin_config.py`).
 *
 * Shares `pluginConfigChanges` with the plugin's own `host.config` (#505):
 * each applied save is published there, and a save the plugin made itself
 * reloads this page's state.
 */
export function usePluginConfigController(pluginId: string) {
  const [snapshot, setSnapshot] = useState<PluginConfigSnapshot | null>(null);
  const [draft, setDraft] = useState<PluginConfigValues | null>(null);
  const [loadError, setLoadError] = useState("");
  const [savePhase, setSavePhase] = useState<DraftSavePhase>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const loadRequestIdRef = useRef(0);
  const client = useMemo(() => createPluginBridgeClient(), []);
  // This controller's identity on the change channel, to tell its own saves from the plugin's.
  const [origin] = useState(() => ({}));

  const [queue] = useState(() => new SerialDraftQueue<PluginConfigValues, PluginConfigSaveResult>({
    isEqual: valuesEqual,
    clone: cloneValues,
    attempt: async (values, operationId) => {
      try {
        const result = await client.setConfig(pluginId, values, { operationId });
        return { ok: true, result };
      } catch (error) {
        if (error instanceof PluginBridgeError) {
          return {
            ok: false,
            resumesAutomatically: RECOVERABLE_WITHOUT_RELOAD.has(error.code),
            message: error.message,
          };
        }
        throw error;
      }
    },
    onApplied: (result) => {
      pluginConfigChanges.publish(pluginId, result.values, origin);
      setSnapshot((current) => (current ? { ...current, values: result.values, envStatus: result.envStatus } : current));
      setDraft(cloneValues(result.values));
    },
    onStatus: (phase, message) => {
      setSavePhase(phase);
      setStatusMessage(message);
    },
  }));

  const load = useCallback(async () => {
    const requestId = ++loadRequestIdRef.current;
    try {
      const loaded = await client.getConfig(pluginId);
      if (loadRequestIdRef.current !== requestId) return;
      queue.reset();
      setSnapshot(loaded);
      setDraft(cloneValues(loaded.values));
      setLoadError("");
      setSavePhase("idle");
      setStatusMessage("");
    } catch (error) {
      if (loadRequestIdRef.current !== requestId) return;
      setLoadError(error instanceof Error ? error.message : String(error));
    }
  }, [client, pluginId, queue]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => pluginConfigChanges.subscribe(pluginId, (_values, from) => {
    // Reload rather than adopt the values: the snapshot also carries env status.
    if (from !== origin) void load();
  }), [load, origin, pluginId]);
  useEffect(() => () => { loadRequestIdRef.current += 1; }, []);
  useEffect(() => {
    if (snapshot && draft) queue.enqueue(draft, snapshot.values);
  }, [draft, snapshot, queue]);

  const updateDraft = useCallback((mutator: (current: PluginConfigValues) => PluginConfigValues) => {
    setDraft((current) => {
      if (!current) return current;
      const next = mutator(cloneValues(current));
      return valuesEqual(current, next) ? current : next;
    });
  }, []);

  return {
    schema: snapshot?.schema ?? null,
    envStatus: snapshot?.envStatus ?? null,
    draft,
    loadError,
    savePhase,
    statusMessage,
    updateDraft,
    retrySave: () => queue.retry(),
    reloadConfig: () => void load(),
  };
}
