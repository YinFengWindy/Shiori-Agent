import { useEffect, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { HerdrSession, SessionListResponse } from "./types";

/**
 * The local Herdr sessions from `sessions.list`, read on mount and on
 * `reload()`. The RPC exists only while the plugin runs and fails when Herdr
 * is missing, so the failure is kept as `error` rather than thrown.
 */
export function useHerdrSessions(client: PluginRpcClient) {
  const [state, setState] = useState<{ sessions: HerdrSession[] | null; error: string | null }>({ sessions: null, error: null });
  const [reads, setReads] = useState(0);

  useEffect(() => {
    let active = true;
    client.call<SessionListResponse>("sessions.list").then(
      (response) => { if (active) setState({ sessions: response.sessions, error: null }); },
      (error: unknown) => { if (active) setState({ sessions: null, error: errorMessage(error) }); },
    );
    return () => { active = false; };
  }, [client, reads]);

  return { ...state, reload: () => setReads((count) => count + 1) };
}
