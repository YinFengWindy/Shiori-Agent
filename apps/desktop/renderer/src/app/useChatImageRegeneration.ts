import { useRef, useState } from "react";
import type { ChatImageHistoryEntry } from "../chat/chatImageHistory";
import type { SessionMessage, SessionPayload, SessionSummary } from "../shared/types";
import {
  mergeSessionSummaryAndMessage,
  parseSessionMessageUpdatePayload,
} from "./useDesktopSessionState";

type UseChatImageRegenerationArgs = {
  activeSessionKey: string;
  selectedChatImageEntry: ChatImageHistoryEntry | null;
  updateCommittedActiveSession: (
    updater: (current: SessionPayload | null) => SessionPayload | null,
  ) => void;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
};

/** Applies a regenerated message only while its original session remains active. */
export function applyRegeneratedSession(
  current: SessionPayload | null,
  targetSessionKey: string,
  summary: SessionSummary,
  message: SessionMessage,
): SessionPayload | null {
  if (current?.key !== targetSessionKey || summary.key !== targetSessionKey) {
    return current;
  }
  return mergeSessionSummaryAndMessage(current, summary, message);
}

/** Owns desktop-only NovelAI regeneration state for chat image history entries. */
export function useChatImageRegeneration({
  activeSessionKey,
  selectedChatImageEntry,
  updateCommittedActiveSession,
  setError,
  setNotice,
}: UseChatImageRegenerationArgs) {
  const regeneratingKeysRef = useRef<Set<string>>(new Set());
  const [regeneratingKeys, setRegeneratingKeys] = useState<ReadonlySet<string>>(new Set());

  async function regenerateSelectedChatImage(): Promise<void> {
    const target = selectedChatImageEntry;
    const targetSessionKey = activeSessionKey;
    if (!targetSessionKey || !target?.messageId || regeneratingKeysRef.current.has(target.historyKey)) {
      return;
    }
    regeneratingKeysRef.current.add(target.historyKey);
    setRegeneratingKeys(new Set(regeneratingKeysRef.current));
    setError("");
    try {
      const res = await window.miraDesktop.invoke({
        method: "novelai.regenerateMessageMedia",
        payload: {
          session_key: targetSessionKey,
          message_id: target.messageId,
          media_index: target.mediaIndex,
        },
      });
      if (res.error) {
        setError(res.error.message);
        return;
      }
      const update = parseSessionMessageUpdatePayload(res.payload);
      if (!update || !update.message || update.session.key !== targetSessionKey) {
        setError("重新生成返回了不匹配的会话。");
        return;
      }
      const regeneratedMessage = update.message;
      updateCommittedActiveSession((current) => (
        applyRegeneratedSession(current, targetSessionKey, update.session, regeneratedMessage)
      ));
      setNotice("图片已重新生成。");
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      regeneratingKeysRef.current.delete(target.historyKey);
      setRegeneratingKeys(new Set(regeneratingKeysRef.current));
    }
  }

  return {
    regenerateSelectedChatImage,
    regeneratingSelectedChatImage: Boolean(
      selectedChatImageEntry
      && regeneratingKeys.has(selectedChatImageEntry.historyKey)
    ),
  };
}
