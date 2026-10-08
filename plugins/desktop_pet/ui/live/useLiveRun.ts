import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { LiveStatus } from "./liveContracts";
import { isRunActive } from "./liveStatusView";
import { useSerialPoll } from "./useSerialPoll";

/** How often an open dialog refreshes the status of an active run (there are no push events). */
export const liveStatusPollIntervalMs = 2000;

/** The run-control RPCs; each answers with the status. */
export type LiveAction = "start" | "pause" | "resume" | "stop";

function sameStatus(a: LiveStatus | null, b: LiveStatus) {
  return a !== null && JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The role's live run (#724): its status and the run controls. The status is
 * read whenever the dialog opens and, while it stays open, polled one request
 * at a time for as long as a run is active. A status read that started
 * before a run-control request is dropped, so it never undoes that request's
 * answer; an unchanged status keeps its object, so polling re-renders nothing.
 */
export function useLiveRun(client: PluginRpcClient, roleId: string, open: boolean) {
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [readError, setReadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState<LiveAction | null>(null);
  // Bumped by every run-control request; not a mirror of rendered state.
  const actions = useRef(0);

  const refresh = useCallback(async () => {
    const since = actions.current;
    try {
      const next = await client.call<LiveStatus>("live.status", { role_id: roleId });
      if (since !== actions.current) return;
      setStatus((current) => sameStatus(current, next) ? current : next);
      setReadError("");
    } catch (cause) {
      if (since === actions.current) setReadError(errorMessage(cause));
    }
  }, [client, roleId]);

  useEffect(() => { if (open) void refresh(); }, [open, refresh]);
  useSerialPoll(open && isRunActive(status), liveStatusPollIntervalMs, refresh);

  const act = async (action: LiveAction) => {
    actions.current += 1;
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
