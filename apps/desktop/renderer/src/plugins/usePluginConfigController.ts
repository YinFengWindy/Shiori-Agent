import { SerialDraftQueue, autosaveDebounceMs, errorFeedback } from "@yinfengwindy/shiori-sdk/host-internal";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type DraftSavePhase, type PluginConfigValues, PluginBridgeError } from "@yinfengwindy/shiori-sdk";
import {
  createPluginBridgeClient,
  type PluginConfigSaveResult,
  type PluginConfigSnapshot,
} from "./pluginBridgeClient";
import { pluginConfigChanges } from "./pluginConfigChanges";

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
  const [{ snapshot, draft }, setConfig] = useState<{
    snapshot: PluginConfigSnapshot | null; draft: PluginConfigValues | null;
  }>({ snapshot: null, draft: null });
  const [loadError, setLoadError] = useState("");
  const [loadDetail, setLoadDetail] = useState("");
  const [statusDetail, setStatusDetail] = useState("");
  const [savePhase, setSavePhase] = useState<DraftSavePhase>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const loadRequestIdRef = useRef(0);
  const client = useMemo(() => createPluginBridgeClient(), []);
  // This controller's identity on the change channel, to tell its own saves from the plugin's.
  const [origin] = useState(() => ({}));

  const [queue] = useState(() => new SerialDraftQueue<PluginConfigValues, PluginConfigSaveResult>({
    debounceMs: autosaveDebounceMs,
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
            ...errorFeedback(error, "插件配置保存失败"),
            ...(["bridge_timeout", "bridge_exit", "bridge_write_failed"].includes(error.code) ? { phase: "unknown" as const, message: "暂时无法确认插件配置保存结果，请重试以确认" } : {}),
          };
        }
        throw error;
      }
    },
    onApplied: (result, submitted) => {
      pluginConfigChanges.publish(pluginId, result.values, origin);
      setConfig((current) => ({
        snapshot: current.snapshot ? { ...current.snapshot, values: result.values, envStatus: result.envStatus } : null,
        draft: valuesEqual(current.draft, submitted) ? cloneValues(result.values) : current.draft,
      }));
    },
    onStatus: (phase, message, detail) => {
      setStatusDetail(detail ?? "");
      setSavePhase(phase);
      setStatusMessage(message);
    },
  }));

  const load = useCallback(async (mode: "replace" | "refresh" = "replace") => {
    const requestId = ++loadRequestIdRef.current;
    try {
      const loaded = await client.getConfig(pluginId);
      if (loadRequestIdRef.current !== requestId) return;
      const refresh = mode === "refresh";
      const pending = queue.hasPendingWork;
      if (!refresh) {
        queue.reset();
        setSavePhase("idle");
        setStatusMessage("");
      }
      // An external save refreshes persistence metadata, but cannot discard this
      // editor's work. Check state too: enqueue's effect may not have run yet.
      setConfig((current) => ({
        snapshot: loaded,
        draft: refresh && current.draft && (pending || !valuesEqual(current.draft, current.snapshot?.values ?? null))
          ? current.draft : cloneValues(loaded.values),
      }));
      setLoadError("");
    } catch (error) {
      if (loadRequestIdRef.current !== requestId) return;
      const failure = errorFeedback(error, "插件配置读取失败");
      setLoadError(failure.message);
      setLoadDetail(failure.detail);
    }
  }, [client, pluginId, queue]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => pluginConfigChanges.subscribe(pluginId, (_values, from) => {
    if (from === origin) {
      // A read started before our acknowledgement cannot restore an older snapshot.
      loadRequestIdRef.current += 1;
    } else {
      // Refresh metadata without resetting a local draft or its failed operation ID.
      void load("refresh");
    }
  }), [load, origin, pluginId]);
  useEffect(() => () => {
    loadRequestIdRef.current += 1;
    queue.flush();
  }, [queue]);
  useEffect(() => {
    if (snapshot && draft) queue.enqueue(draft, snapshot.values);
  }, [draft, snapshot, queue]);

  const updateDraft = useCallback((mutator: (current: PluginConfigValues) => PluginConfigValues) => {
    loadRequestIdRef.current += 1;
    setConfig((current) => {
      if (!current.draft) return current;
      const next = mutator(cloneValues(current.draft));
      return valuesEqual(current.draft, next) ? current : { ...current, draft: next };
    });
  }, []);

  return {
    schema: snapshot?.schema ?? null,
    envStatus: snapshot?.envStatus ?? null,
    draft,
    loadError,
    loadDetail,
    statusDetail,
    savePhase,
    statusMessage,
    updateDraft,
    retrySave: () => queue.retry(),
    reloadConfig: () => void load(),
  };
}
