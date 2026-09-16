import { pluginRuntimeChanged } from "./pluginRuntimeChanged";
import { useEffect, useMemo, useState } from "react";
import { createPluginRpcClient } from "./pluginBridgeClient";

/** Owns a mounted contribution's client and replaces it on runtime publication. */
export function usePluginRpcClient(pluginId: string) {
  const [generation, setGeneration] = useState(0);
  const { client } = useMemo(() => ({ client: createPluginRpcClient(pluginId), generation }), [pluginId, generation]);
  useEffect(() => window.miraDesktop.onEvent((event) => {
    // Existing clients invalidate on exit; renew only once a bridge is ready.
    if (pluginRuntimeChanged(event) && event.method !== "bridge.exit") setGeneration((value) => value + 1);
  }), []);
  useEffect(() => () => { void client.dispose(); }, [client]);
  return client;
}
