import { useEffect, useState } from "react";
import { errorMessage, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { readAffectionChatStatus, type AffectionChatStatus } from "./chatStatus";

/** The plugin's own event after a role's data changed outside a turn (heartbeat, snapshot refresh). */
export const affectionStatusChangedEvent = "plugin.affection.chat_status.changed";

/**
 * The role's sidebar data, re-read whenever it may have changed.
 *
 * The host broadcasts `session.updated` (with `role_id`) once a turn, a
 * proactive message or a channel turn is stored; affection is applied before
 * that, so the re-read sees the new value. The plugin's backend emits
 * `chat_status.changed` after each loneliness heartbeat (which also settles
 * decay) and snapshot refresh. The caller keys the component by role, so one
 * hook instance serves one role.
 */
export function useAffectionChatStatus(client: PluginRpcClient, host: PluginHostServices, roleId: string) {
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState<AffectionChatStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => host.onEvent((event) => {
    const refreshes = event.method === "session.updated" || event.method === affectionStatusChangedEvent;
    if (refreshes && event.payload.role_id === roleId) {
      setRevision((current) => current + 1);
    }
  }), [host, roleId]);

  useEffect(() => {
    let cancelled = false;
    readAffectionChatStatus(client, roleId).then((result) => {
      if (cancelled) return;
      setStatus(result);
      setError("");
    }, (cause: unknown) => {
      if (!cancelled) setError(errorMessage(cause));
    });
    return () => { cancelled = true; };
  }, [client, revision, roleId]);

  return { status, error };
}
