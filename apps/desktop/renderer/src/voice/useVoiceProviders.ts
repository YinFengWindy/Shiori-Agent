import { useEffect, useState } from "react";
import { errorMessage } from "@yinfengwindy/shiori-sdk";
import type { VoiceProviderDescriptor } from "../../../src/bridge/shared";
import { pluginRosterChanged } from "../plugins/pluginRuntimeChanged";
import { invokeBridgePayload } from "../shared/bridgeInvoke";

/** Tracks plugin speech capabilities and rejects stale discovery after runtime changes. */
export function useVoiceProviders(enabled = true) {
  const [state, setState] = useState<{ providers: VoiceProviderDescriptor[]; loading: boolean; error: string }>({ providers: [], loading: enabled, error: "" });
  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let revision = 0;
    const reload = async () => {
      const requestRevision = ++revision;
      setState({ providers: [], loading: true, error: "" });
      try {
        const result = await invokeBridgePayload<{ providers: VoiceProviderDescriptor[] }>(window.miraDesktop.invoke, "voice.providers", {});
        if (!disposed && revision === requestRevision) setState({ providers: result.providers, loading: false, error: "" });
      } catch (error) {
        if (!disposed && revision === requestRevision) setState({ providers: [], loading: false, error: `语音服务商读取失败：${errorMessage(error)}` });
      }
    };
    void reload();
    const unsubscribe = window.miraDesktop.onEvent((event) => {
      if (event.method === "bridge.exit") {
        // Discovery must not restart a stopped backend just to refresh this view.
        revision += 1;
        setState({ providers: [], loading: false, error: "语音服务暂不可用" });
      } else if (pluginRosterChanged(event)) void reload();
    });
    return () => { disposed = true; revision += 1; unsubscribe(); };
  }, [enabled]);
  return state;
}
