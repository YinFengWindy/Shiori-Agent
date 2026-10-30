import { useEffect, useState } from "react";
import { errorMessage, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { readAffectionChatStatus, type AffectionChatStatus } from "./chatStatus";

/**
 * The role's sidebar data, re-read after each committed turn of that role.
 *
 * The host broadcasts `session.updated` (with `role_id`) once a turn, a
 * proactive message or a channel turn is stored; affection is applied before
 * that, so the re-read sees the new value. The caller keys the component by
 * role, so one hook instance serves one role.
 */
export function useAffectionChatStatus(client: PluginRpcClient, host: PluginHostServices, roleId: string) {
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState<AffectionChatStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => host.onEvent((event) => {
    if (event.method === "session.updated" && event.payload.role_id === roleId) {
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
