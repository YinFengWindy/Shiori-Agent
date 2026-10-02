import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";
import { errorFeedback } from "@shiori/sdk/host-internal";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import { subscribeChatModelChanges } from "./chatModelChanges";
import { contextResultLabel, mergeContextStatus, type ChatContextStatus } from "./chatContextState";
import { compactChatContext } from "./chatContextActions";

/** Loads and refreshes the active persisted context without reading composer drafts. */
export function useChatContext(activeRoleId: string, sessionKey: string, bridgeReady: boolean, sending: boolean) {
  const [status, setStatus] = useState<ChatContextStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  // Status reads: a newer read, model change or scope change makes older reads stale.
  const generation = useRef(0);
  // Compaction ownership ends only with the role/session scope, never with sending
  // or bridge reconnection, so a running operation always delivers its feedback.
  const operation = useRef<symbol | null>(null);
  const invalidate = useCallback(() => { ++generation.current; }, []);

  const refresh = useCallback(async () => {
    const ticket = ++generation.current;
    if (!activeRoleId || !bridgeReady) return;
    try {
      const next = await invokeBridgePayload<ChatContextStatus>(window.miraDesktop.invoke, "chat.context.status", { role_id: activeRoleId });
      if (ticket === generation.current && next.session_key === sessionKey) setStatus((previous) => mergeContextStatus(previous, next));
    } catch (error) {
      if (ticket === generation.current) {
        setStatus(null);
        setNotice(errorFeedback(error, "上下文用量暂不可用，请稍后重试").message);
      }
    }
  }, [activeRoleId, bridgeReady, sessionKey]);
  // Subscriptions live per scope but must read with the latest bridge state.
  const refreshLatest = useEffectEvent(() => { void refresh(); });

  useEffect(() => {
    setStatus(null);
    setNotice("");
    setBusy(false);
    operation.current = null;
    const offModels = subscribeChatModelChanges((roleId, pending) => {
      if (roleId !== activeRoleId) return;
      ++generation.current;
      setStatus(null);
      setNotice(pending ? "正在切换模型" : "");
      if (!pending) refreshLatest();
    });
    const off = window.miraDesktop.onEvent((event) => {
      if (["runtime.applied", "roles.updated", "identities.updated"].includes(event.method)) {
        ++generation.current;
        setStatus(null);
        refreshLatest();
      } else if (event.method === "chat.context.updated" && event.payload.session_key === sessionKey && !operation.current) {
        // The host publishes this once a role turn releases its gate; the turn's
        // chat.done / session.updated would only repeat the same read.
        refreshLatest();
      }
    });
    return () => { invalidate(); operation.current = null; off(); offModels(); };
  }, [activeRoleId, invalidate, sessionKey]);

  // Scope changes and reconnection re-read usage; the last known value stays meanwhile.
  useEffect(() => { void refresh(); }, [refresh]);

  const unavailable = !bridgeReady ? "桌面服务未连接" : !activeRoleId ? "请选择角色" : sending ? "正在回复" : busy ? "正在整理记忆并压缩上下文" : status?.busy ? status.reason : "";
  const compact = useCallback(async () => {
    if (operation.current || sending || !bridgeReady || !status?.can_compact || status.busy) {
      const reason = unavailable || status?.reason || "上下文用量未知，请稍后重试";
      setNotice(reason);
      feedback.info(reason);
      return;
    }
    const owner = Symbol("context-compaction");
    const owned = () => operation.current === owner;
    operation.current = owner;
    setBusy(true);
    setNotice("");
    const ticket = ++generation.current;
    try {
      const result = await compactChatContext(activeRoleId, owned);
      if (!owned() || result.session_key !== sessionKey) return;
      // A status read started meanwhile (e.g. after a model change) is newer.
      if (ticket === generation.current) setStatus(result);
      setNotice(contextResultLabel(result));
    } catch (error) {
      if (owned()) {
        const failure = errorFeedback(error, "上下文操作未完成，请稍后重试");
        const message = `压缩失败：${failure.message}`;
        setNotice(message);
        feedback.error(message, { detail: failure.detail });
      }
    } finally {
      // Even a superseded result refreshes; scope cleanup revokes ownership on
      // role changes and unmount.
      if (owned()) {
        operation.current = null;
        setBusy(false);
        await refresh();
      }
    }
  }, [activeRoleId, bridgeReady, refresh, sending, sessionKey, status, unavailable]);

  return { status, busy: busy || Boolean(status?.busy), notice, unavailable, compact, refresh };
}
