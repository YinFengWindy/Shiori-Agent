import { pluginContextReplaced } from "./pluginRuntimeChanged";
import { useEffect, useMemo, useState } from "react";
import { createPluginRpcClient } from "./pluginBridgeClient";

/** Owns a contribution instance and its client; bindings key only the plugin subtree by generation. */
export function usePluginRpcScope(pluginId: string) {
  const [generation, setGeneration] = useState(0);
  const scope = useMemo(() => ({ client: createPluginRpcClient(pluginId), generation }), [pluginId, generation]);
  useEffect(() => window.miraDesktop.onEvent((event) => {
    // Existing clients invalidate on exit; renew only once a bridge is ready.
    if (pluginContextReplaced(event, pluginId) && event.method !== "bridge.exit") setGeneration((value) => value + 1);
  }), [pluginId]);
  useEffect(() => () => { void scope.client.dispose(); }, [scope]);
  return scope;
}

/** A client consumer without a contributed subtree uses the same instance owner. */
export function usePluginRpcClient(pluginId: string) {
  return usePluginRpcScope(pluginId).client;
}
