import { useCallback, useEffect, useRef, useState } from "react";
import { errorFeedback } from "@shiori/sdk/host-internal";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import { subscribeChatModelChanges } from "./chatModelChanges";
import { contextResultLabel, type ChatContextStatus } from "./chatContextState";
import { compactChatContext } from "./chatContextActions";

/** Loads and refreshes the active persisted context without reading composer drafts. */
export function useChatContext(activeRoleId: string, sessionKey: string, bridgeReady: boolean, sending: boolean) {
  const [status, setStatus] = useState<ChatContextStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const generation = useRef(0);
  const operation = useRef<symbol | null>(null);
  const invalidate = useCallback(() => { ++generation.current; }, []);

  const refresh = useCallback(async () => {
    const ticket = ++generation.current;
    if (!activeRoleId || !bridgeReady || sending) return;
    try {
      const next = await invokeBridgePayload<ChatContextStatus>(window.miraDesktop.invoke, "chat.context.status", { role_id: activeRoleId });
      if (ticket === generation.current && next.session_key === sessionKey) setStatus(next);
    } catch (error) {
      if (ticket === generation.current) {
        setStatus(null);
        setNotice(errorFeedback(error, "上下文用量暂不可用，请稍后重试").message);
      }
    }
  }, [activeRoleId, bridgeReady, sending, sessionKey]);

  useEffect(() => {
    setStatus(null);
    setNotice("");
    setBusy(false);
    operation.current = null;
    void refresh();
    const offModels = subscribeChatModelChanges((roleId, pending) => {
      if (roleId !== activeRoleId) return;
      ++generation.current;
      setStatus(null);
      setNotice(pending ? "正在切换模型" : "");
      if (!pending) void refresh();
    });
    const off = window.miraDesktop.onEvent((event) => {
      if (["runtime.applied", "roles.updated", "identities.updated"].includes(event.method)) {
        ++generation.current;
        setStatus(null);
        void refresh();
      } else if (["session.updated", "chat.done", "chat.error", "chat.context.updated"].includes(event.method)
        && (event.payload.session_key === sessionKey || (event.payload.session as { key?: string } | undefined)?.key === sessionKey)) {
        if (!operation.current) void refresh();
      }
    });
    return () => { invalidate(); off(); offModels(); };
  }, [activeRoleId, invalidate, refresh, sessionKey]);

  const unavailable = !bridgeReady ? "桌面服务未连接" : !activeRoleId ? "请选择角色" : sending ? "正在回复" : busy ? "正在整理记忆并压缩上下文" : status?.busy ? status.reason : "";
  const compact = useCallback(async () => {
    if (operation.current || sending || !bridgeReady || !status?.can_compact || status.busy) {
      const reason = unavailable || status?.reason || "上下文用量未知，请稍后重试";
      setNotice(reason);
      feedback.info(reason);
      return;
    }
    const owner = Symbol("context-compaction");
    operation.current = owner;
    setBusy(true);
    setNotice("");
    const ticket = ++generation.current;
    try {
      const result = await compactChatContext(activeRoleId, () => ticket === generation.current);
      if (ticket !== generation.current || result.session_key !== sessionKey) return;
      setStatus(result);
      const message = contextResultLabel(result);
      setNotice(message);
      await refresh();
    } catch (error) {
      if (ticket === generation.current) {
        const failure = errorFeedback(error, "上下文操作未完成，请稍后重试");
        const message = `压缩失败：${failure.message}`;
        setNotice(message);
        feedback.error(message, { detail: failure.detail });
      }
    } finally {
      // Scope cleanup owns new contexts; a late operation cannot unlock them.
      if (operation.current === owner) {
        operation.current = null;
        setBusy(false);
      }
    }
  }, [activeRoleId, bridgeReady, refresh, sending, sessionKey, status, unavailable]);

  return { status, busy: busy || Boolean(status?.busy), notice, unavailable, compact, refresh };
}
