import { useCallback, useEffect, useEffectEvent, useState, useSyncExternalStore } from "react";
import { ChatContextCache } from "./chatContextCache";
import { subscribeChatModelChanges } from "./chatModelChanges";

/** Own cached usage and its bridge invalidation lifecycle for one mounted composer. */
export function useChatContextStatus(roleId: string, sessionKey: string, bridgeReady: boolean, sending: boolean, compacting: boolean) {
  const [cache] = useState(() => new ChatContextCache());
  const getSnapshot = () => cache.get(roleId, sessionKey);
  const snapshot = useSyncExternalStore(cache.subscribe, getSnapshot, getSnapshot);
  const read = useCallback(async () => {
    if (bridgeReady && !sending) await cache.read(roleId, sessionKey);
  }, [bridgeReady, cache, roleId, sending, sessionKey]);
  const refresh = useCallback(async () => {
    cache.invalidate({ roleId, sessionKey });
    await read();
  }, [cache, read, roleId, sessionKey]);
  const readLatest = useEffectEvent(() => { void read(); });
  const onContextChanged = useEffectEvent((changedSession: string) => {
    cache.invalidate({ sessionKey: changedSession });
    if (changedSession === sessionKey && !compacting) readLatest();
  });
  const onTurnFinished = useEffectEvent(async (changedSession: string) => {
    if (changedSession !== sessionKey || compacting || !bridgeReady) return;
    // Context notification can precede the desktop turn's terminal event. Join
    // its read, then retry once only if the host still reported a busy budget.
    await cache.finishTurn(roleId, sessionKey);
  });

  useEffect(() => {
    const offModels = subscribeChatModelChanges((changedRole, pending) => {
      cache.setModelPending(changedRole, pending);
      if (!pending) readLatest();
    });
    const offEvents = window.miraDesktop.onEvent((event) => {
      if (["runtime.applied", "identities.updated", "roles.updated"].includes(event.method)) {
        const changedRole = event.method === "roles.updated" ? event.payload.role_id : undefined;
        cache.invalidate(typeof changedRole === "string" ? { roleId: changedRole } : {}, true);
        readLatest();
      } else if (event.method === "chat.context.updated") {
        onContextChanged(String(event.payload.session_key ?? ""));
      } else if (event.method === "session.updated" && event.payload.change === "message_appended"
        && (event.id === "proactive" || event.id.startsWith("proactive:"))) {
        // DesktopBridgeService's standalone push/proactive commits have no
        // guaranteed context event. Normal turn and metadata updates do.
        onContextChanged(String(event.payload.session_key ?? ""));
      } else if (event.method === "chat.done" || event.method === "chat.error") {
        void onTurnFinished(String(event.payload.session_key ?? ""));
      }
    });
    return () => { offEvents(); offModels(); cache.clear(); };
  }, [cache]);

  useEffect(() => {
    // Keep the last usage visible while disconnected, but never reuse its
    // freshness (including another role's) after the host restarts.
    if (!bridgeReady) cache.invalidate();
  }, [bridgeReady, cache]);
  useEffect(() => {
    cache.setNotice(roleId, sessionKey, "");
  }, [cache, roleId, sessionKey]);
  useEffect(() => {
    if (sending) cache.invalidate({ roleId, sessionKey });
    else void read();
  }, [cache, read, roleId, sending, sessionKey]);

  return {
    ...snapshot, refresh,
    beginUpdate: () => cache.beginUpdate(roleId, sessionKey),
  };
}
