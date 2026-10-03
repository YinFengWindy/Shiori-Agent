import { useCallback, useEffect, useRef, useState } from "react";
import { useLatestRef } from "@yinfengwindy/shiori-sdk";
import { errorFeedback } from "@yinfengwindy/shiori-sdk/host-internal";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import { contextResultLabel } from "./chatContextState";
import { compactChatContext } from "./chatContextActions";
import { useChatContextStatus } from "./useChatContextStatus";

/** Loads and refreshes the active persisted context without reading composer drafts. */
export function useChatContext(activeRoleId: string, sessionKey: string, bridgeReady: boolean, sending: boolean) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const { status, notice: statusNotice, refresh, beginUpdate } = useChatContextStatus(activeRoleId, sessionKey, bridgeReady, sending, busy);
  const refreshRef = useLatestRef(refresh);
  // Compaction ownership ends only with the role/session scope, never with sending
  // or bridge reconnection, so a running operation always delivers its feedback.
  const operation = useRef<symbol | null>(null);

  useEffect(() => {
    setBusy(false);
    setNotice("");
    operation.current = null;
    return () => { operation.current = null; };
  }, [activeRoleId, sessionKey]);

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
    const update = beginUpdate();
    try {
      const result = await compactChatContext(activeRoleId, owned);
      if (!owned() || result.session_key !== sessionKey) return;
      // A status read started meanwhile (e.g. after a model change) is newer.
      update.accept(result);
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
        await refreshRef.current();
      }
    }
  }, [activeRoleId, beginUpdate, bridgeReady, refreshRef, sending, sessionKey, setNotice, status, unavailable]);

  return { status, busy: busy || Boolean(status?.busy), notice: statusNotice || notice, unavailable, compact, refresh };
}
