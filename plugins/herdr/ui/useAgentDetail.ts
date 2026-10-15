import { useEffect, useMemo, useSyncExternalStore } from "react";
import type { PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { mergeUnchanged } from "./dashboardStore";
import { TaskFeed } from "./taskFeed";
import type { AgentDetailResponse } from "./types";

/** Polls one agent's state and terminal output while its view is mounted. */
export function useAgentDetail(client: PluginRpcClient, host: PluginHostServices, paneId: string, pollMs: number) {
  const feed = useMemo(() => new TaskFeed<AgentDetailResponse>({
    read: (rpc) => rpc.call<AgentDetailResponse>("agents.get", { pane_id: paneId }),
    merge: mergeUnchanged,
    pollMs,
  }), [paneId, pollMs]);
  useEffect(() => {
    void feed.start(client, host);
    return () => feed.stop();
  }, [feed, client, host]);
  return useSyncExternalStore(feed.subscribe, feed.getSnapshot, feed.getSnapshot);
}
