import { useEffect, useSyncExternalStore } from "react";
import { errorFeedback } from "@yinfengwindy/shiori-sdk/host-internal";
import { mascotFeedback } from "../shared/mascot/mascotFeedback";
import { createPluginBridgeClient } from "./pluginBridgeClient";
import { refreshPluginEnabledState } from "./pluginEnabledStateStore";
import { PluginTrustDialog } from "./PluginTrustDialog";
import { pluginTrustQueue } from "./pluginTrustQueue";

/** Host-owned confirmation appears without executing any code from the candidate. */
export function PluginTrustHost({ ready }: { ready: boolean }) {
  const state = useSyncExternalStore(pluginTrustQueue.subscribe, pluginTrustQueue.getSnapshot);
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    void window.miraDesktop.applicationSessionId().then(async (session) => {
      if (cancelled) return;
      pluginTrustQueue.initialize(session, window.localStorage);
      await refreshPluginEnabledState();
    }).catch((error: unknown) => {
      if (!cancelled) mascotFeedback.error(errorFeedback(error, "插件信任检查失败").message);
    });
    return () => { cancelled = true; };
  }, [ready]);

  return <PluginTrustDialog plugin={ready ? state.request?.plugin ?? null : null}
    enable={state.request?.enable} busy={state.busy} confirmDisabled={state.stale}
    error={state.error} onClose={() => pluginTrustQueue.dismiss()} onConfirm={() => void confirmPluginTrust()} />;
}

/** Reconcile even a lost response against the current host state before closing. */
async function confirmPluginTrust() {
  const request = pluginTrustQueue.begin();
  if (!request) return;
  const client = createPluginBridgeClient();
  let operationError: unknown;
  try {
    await client.trustPlugin(request.plugin.candidateId, request.plugin.trustFingerprint!, {
      enable: request.enable, operationId: request.operationId,
    });
  } catch (error) {
    operationError = error;
  }
  try {
    const plugins = await refreshPluginEnabledState(client);
    const current = plugins.find((plugin) => plugin.candidateId === request.plugin.candidateId);
    if (!current || current.contentFingerprint !== request.plugin.trustFingerprint || !current.trusted || current.canTrust) {
      pluginTrustQueue.fail(errorFeedback(operationError, "插件尚未获得信任，请重新确认。").message);
      return;
    }
    pluginTrustQueue.complete();
    if (["FAILED", "RESTART_REQUIRED", "BLOCKED", "CONFLICT"].includes(current.state)) {
      mascotFeedback.error(current.error || "信任已保存，插件未能启动。请查看插件状态。");
    } else if (operationError && (request.enable || request.plugin.enabled) && current.state !== "ACTIVE") {
      mascotFeedback.error(errorFeedback(operationError, "信任已保存，插件尚未启动。请查看插件状态。").message);
    }
  } catch (error) {
    pluginTrustQueue.fail(errorFeedback(error, "无法确认插件当前状态，请重试。").message);
  }
}
