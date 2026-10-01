import { useEffect, useSyncExternalStore } from "react";
import {
  ensurePluginEnabledStateLoaded,
  getPluginEnabledPredicate,
  isPluginRosterLoaded,
  subscribePluginEnabledState,
} from "./pluginEnabledStateStore";
import { errorMessage } from "@shiori/plugin-sdk";

/**
 * Subscribes to the shared plugin-enabled cache and triggers its first
 * load. Uses `useSyncExternalStore` (rather than a hand-rolled
 * subscribe/`useReducer` pair) so React can correctly interleave this
 * external store with concurrent rendering, and returns the store's own
 * predicate reference — which changes identity on every update — instead of
 * a fixed module-level function, so a consumer that memoizes against it
 * recomputes instead of reading a stale result.
 */
export function usePluginEnabledState(): (pluginId: string) => boolean {
  const isPluginEnabled = useSyncExternalStore(
    subscribePluginEnabledState,
    getPluginEnabledPredicate,
    getPluginEnabledPredicate,
  );
  useEffect(() => {
    // This mount-time load is a boundary with nothing to show: the user already
    // sees an unreachable bridge (offline banner / onboarding error), and the
    // bridge lifecycle refresh reports roster failures as feedback. Record it
    // as a diagnostic instead of leaving an unhandled rejection.
    ensurePluginEnabledStateLoaded().catch((error: unknown) => {
      window.miraDesktop.reportRendererDiagnostic({
        kind: "error",
        message: `插件状态加载失败：${errorMessage(error, { includeDetail: true })}`,
        stack: error instanceof Error ? error.stack : undefined,
      });
    });
  }, []);
  return isPluginEnabled;
}

/**
 * Whether the plugin roster has loaded once. Pair with `usePluginEnabledState`
 * (which triggers the load) when "not yet known" must render differently from
 * "disabled".
 */
export function usePluginRosterLoaded() {
  return useSyncExternalStore(subscribePluginEnabledState, isPluginRosterLoaded, isPluginRosterLoaded);
}
