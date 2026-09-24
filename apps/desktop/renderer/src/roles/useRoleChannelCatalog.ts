import { useCallback, useEffect, useRef, useState } from "react";
import { createPluginBridgeClient, type ChannelSummary, type PluginBridgeClient } from "../plugins/pluginBridgeClient";
import { pluginRuntimeChanged } from "../plugins/pluginRuntimeChanged";
import { errorMessage, feedback } from "../shared/feedback/feedbackStore";
import type { RoleChannelCatalog } from "./roleChannelCatalog";

// Lazy about window.miraDesktop, so one module-level instance is safe to build at import time.
const defaultClient = createPluginBridgeClient();

/**
 * Loads `channels.list` for the role delivery panels and reloads it whenever
 * the runtime changes: a plugin toggle, plugin config save or settings save
 * publishes a new generation (`runtime.applied`), and a bridge restart
 * (`bridge.ready`) may change every channel's state. A failed load keeps the
 * last good catalog and reports the error once through the shared feedback.
 */
export function useRoleChannelCatalog(
  client: Pick<PluginBridgeClient, "listChannels"> = defaultClient,
): RoleChannelCatalog {
  const [channels, setChannels] = useState<ChannelSummary[] | null>(null);
  // Responses may resolve out of order when events arrive in a burst; only the latest request may publish.
  const requestRef = useRef(0);

  const reload = useCallback(async () => {
    const request = ++requestRef.current;
    try {
      const next = await client.listChannels();
      if (request === requestRef.current) setChannels(next);
    } catch (error) {
      if (request === requestRef.current) feedback.error(`渠道列表加载失败：${errorMessage(error)}`);
    }
  }, [client]);

  useEffect(() => { void reload(); }, [reload]);

  useEffect(() => window.miraDesktop.onEvent((event) => {
    if (pluginRuntimeChanged(event) && event.method !== "bridge.exit") void reload();
  }), [reload]);

  return channels;
}
