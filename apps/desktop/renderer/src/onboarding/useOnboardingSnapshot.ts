import { useCallback } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { errorMessage } from "../shared/feedback/feedbackStore";
import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";
import { loadOnboardingData } from "./onboardingData";
import type { useDesktopBridgeLifecycle } from "../app/useDesktopBridgeLifecycle";

/** A settings save or plugin change republishes the runtime and may satisfy a prerequisite. */
const refreshEvents: ReadonlySet<string> = new Set(["runtime.applied"]);

/** A stopped bridge invalidates the snapshot; its exit message becomes the error. */
function bridgeExitError(event: BridgeEvent) {
  return event.method === "bridge.exit" ? String(event.payload.message ?? "连接桥已停止。") : null;
}

/** Refreshes first-run prerequisites and invalidates stale responses across bridge restarts. */
export function useOnboardingSnapshot(enabled: boolean, bridgeLifecycle: ReturnType<typeof useDesktopBridgeLifecycle>) {
  const load = useCallback(() => loadOnboardingData(window.miraDesktop), []);
  const snapshot = useBridgeRefreshedValue({ enabled, load, refreshEvents, failOn: bridgeExitError });
  const { refresh, fail, markPending } = snapshot;
  const retry = async () => {
    markPending();
    try {
      const status = await window.miraDesktop.bridgeStatus();
      if (!status.running) {
        await bridgeLifecycle.restartBridge();
      } else await bridgeLifecycle.refreshBridge();
    } catch (error) {
      fail(errorMessage(error));
      return;
    }
    await refresh();
  };
  return { data: snapshot.value, error: snapshot.error, loading: snapshot.loading, refresh, retry };
}
