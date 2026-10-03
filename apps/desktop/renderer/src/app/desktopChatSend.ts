import type { ChatSendFailure } from "../chat/chatSendFailure";
import { errorMessage } from "@yinfengwindy/shiori-sdk";
import { errorFeedback } from "@yinfengwindy/shiori-sdk/host-internal";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import type { useDesktopChatTurns } from "./useDesktopChatTurns";
import type { createDesktopSessionSnapshot } from "./desktopSessionSnapshot";
import { buildOptimisticUserChatMessage, normalizeChatAttachmentPaths } from "../chat/chatComposerState";
import type { ChatSendRequest } from "../shared/types";
import { fetchRoleSession, parseSessionMessageUpdatePayload } from "./desktopSessionProtocol";
import type { createDesktopSessionMessages } from "./desktopSessionMessages";
import type { createDesktopSessionCache } from "./desktopSessionCache";
import { canSendSessionState } from "./desktopSendingSessions";
import { compactChatContext, isCompactCommand } from "../chat/chatContextActions";
type Args = Pick<DesktopSessionStateArgs, "activeRoleIdRef" | "activeSessionRef" | "sendingSessionsRef" | "reportSendFailure">
  & Pick<ReturnType<typeof useDesktopChatTurns>, "pendingUserMessagesRef" | "latestTurnIdsRef" | "markSessionSending" | "isLatestChatTurn" | "isCurrentChatTurn" | "completeChatTurn">
  & Pick<ReturnType<typeof createDesktopSessionSnapshot>, "updateCommittedActiveSession">
  & Pick<ReturnType<typeof createDesktopSessionMessages>, "commitSessionMessageUpdate">
  & Pick<ReturnType<typeof createDesktopSessionCache>, "cacheRoleSession">;
/** Starts a chat turn and recovers its authoritative session when sending fails. */
export function createDesktopChatSend({
  activeRoleIdRef,
  activeSessionRef,
  sendingSessionsRef,
  reportSendFailure,
  pendingUserMessagesRef,
  latestTurnIdsRef,
  markSessionSending,
  isLatestChatTurn,
  isCurrentChatTurn,
  completeChatTurn,
  commitSessionMessageUpdate,
  updateCommittedActiveSession,
  cacheRoleSession
}: Args) {
  async function sendMessage(request: ChatSendRequest): Promise<boolean> {
    const content = request.content.trim();
    const media = normalizeChatAttachmentPaths(request.attachments);
    const currentReplyTarget = request.replyTarget;
    const roleId = activeRoleIdRef.current;
    const previousSession = activeSessionRef.current;
    const sessionKey = previousSession?.key ?? "";
    if ((!content && media.length === 0) || !roleId || !sessionKey) return false;
    if (!canSendSessionState(sendingSessionsRef.current, sessionKey)) return false;
    if (isCompactCommand(content)) {
      try {
        await compactChatContext(roleId, () => activeRoleIdRef.current === roleId && activeSessionRef.current?.key === sessionKey);
      } catch (error) {
        const failure = errorFeedback(error, "上下文操作未完成，请稍后重试");
        reportSendFailure({ message: `压缩失败：${failure.message}`, details: { detail: failure.detail } });
      }
      // No chat was sent: callers must preserve their draft and attachments.
      return false;
    }
    const persistedReplyTarget = currentReplyTarget;
    const clientMessageId = window.crypto.randomUUID();
    const turnId = window.crypto.randomUUID();
    const pendingUserMessage = buildOptimisticUserChatMessage(
      content,
      media,
      persistedReplyTarget,
      clientMessageId,
    );
    pendingUserMessagesRef.current[sessionKey] = pendingUserMessage;
    latestTurnIdsRef.current[sessionKey] = turnId;
    markSessionSending(sessionKey, roleId);
    updateCommittedActiveSession((current) =>
      current?.key === sessionKey
        ? {
            ...current,
            messages: [
              ...current.messages,
              pendingUserMessage,
            ],
          }
        : current,
    );
    const recoverFailedSend = async (failure: ChatSendFailure) => {
      if (!isCurrentChatTurn(sessionKey, turnId)) return;
      delete pendingUserMessagesRef.current[sessionKey];
      const { session: recoveredSession } = await fetchRoleSession(roleId);
      // Bridge resets or a newer turn can supersede this recovery while it awaits.
      if (!isCurrentChatTurn(sessionKey, turnId)) return;
      const restoredSession = recoveredSession ?? previousSession;
      if (restoredSession) {
        cacheRoleSession(roleId, restoredSession);
        updateCommittedActiveSession((current) =>
          current?.key === sessionKey ? restoredSession : current,
        );
      }
      completeChatTurn(sessionKey, turnId);
      reportSendFailure(failure);
    };
    try {
      const res = await window.miraDesktop.invoke({
        method: "chat.send",
        payload: {
          role_id: roleId,
          content,
          media,
          client_message_id: clientMessageId,
          turn_id: turnId,
          reply_to_message_id: persistedReplyTarget?.messageId ?? "",
          reply_to_content: persistedReplyTarget?.content ?? "",
          reply_to_sender: persistedReplyTarget?.sender ?? "",
        },
      });
      if (res.error) {
        await recoverFailedSend(res.error);
        return false;
      }
      const update = parseSessionMessageUpdatePayload(res.payload);
      if (!update || update.session.key !== sessionKey || !update.message) {
        throw new Error("发送消息响应无效");
      }
      // Completion can arrive before this continuation. Reconcile its persisted user
      // message unless a newer turn or bridge reset has superseded the acknowledgement.
      if (isLatestChatTurn(sessionKey, turnId)) commitSessionMessageUpdate(roleId, update);
      return true;
    } catch (error) {
      await recoverFailedSend({ message: errorMessage(error, { includeDetail: true }) });
      return false;
    }
  }

  return { sendMessage };
}
