import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { LiveStatus } from "./liveContracts";
import { isRunActive } from "./liveStatusView";
import { useSerialPoll } from "./useSerialPoll";

/** How often an open dialog refreshes the status of an active run (there are no push events). */
export const liveStatusPollIntervalMs = 2000;

/** The run-control RPCs; each answers with the status. */
export type LiveAction = "start" | "pause" | "resume" | "stop";

// The whole status, counters and recent replies included, is what the panel shows;
// it is a small JSON document, so comparing its serialised form stays exact without a field list to keep in sync.
function sameStatus(a: LiveStatus | null, b: LiveStatus) {
  return a !== null && JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The role's live run (#724): its status and the run controls. The status is
 * read whenever the dialog opens and, while it stays open, polled one request
 * at a time for as long as a run is active. A status read is dropped when
 * any later request (read or run control) started before it answered, so an
 * older answer never undoes a newer one; an unchanged status keeps its object, so polling re-renders nothing.
 */
export function useLiveRun(client: PluginRpcClient, roleId: string, open: boolean) {
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [readError, setReadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState<LiveAction | null>(null);
  // Bumped by every request; not a mirror of rendered state.
  const requests = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++requests.current;
    try {
      const next = await client.call<LiveStatus>("live.status", { role_id: roleId });
      if (id !== requests.current) return;
      setStatus((current) => sameStatus(current, next) ? current : next);
      setReadError("");
    } catch (cause) {
      if (id === requests.current) setReadError(errorMessage(cause));
    }
  }, [client, roleId]);

  useEffect(() => { if (open) void refresh(); }, [open, refresh]);
  useSerialPoll(open && isRunActive(status), liveStatusPollIntervalMs, refresh);

  const act = async (action: LiveAction) => {
    requests.current += 1;
    setPending(action);
    setActionError("");
    try {
      const next = await client.call<LiveStatus>(`live.${action}`, { role_id: roleId });
      setStatus((current) => sameStatus(current, next) ? current : next);
    } catch (cause) {
      // e.g. 开始 refused by a precondition: the backend's reason is shown as is.
      setActionError(errorMessage(cause));
      void refresh();
    } finally {
      setPending(null);
    }
  };

  return { status, readError, actionError, pending, act, reload: () => { void refresh(); } };
}

/** What the run panel reads from and acts through. */
export type LiveRunController = ReturnType<typeof useLiveRun>;
