import { errorMessage } from "@yinfengwindy/shiori-sdk";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import type { useDesktopChatTurns } from "./useDesktopChatTurns";
import type { createDesktopSessionSnapshot } from "./desktopSessionSnapshot";
import { findChatRetryTarget } from "../chat/chatFailedTurn";
import { getChatMessageReactKey } from "../chat/chatMessageIdentity";
import type { ChatSendFailure } from "../chat/chatSendFailure";
import type { createDesktopSessionMessages } from "./desktopSessionMessages";
import { canSendSessionState } from "./desktopSendingSessions";
type Args = Pick<DesktopSessionStateArgs, "activeRoleIdRef" | "activeSessionRef" | "sendingSessionsRef" | "reportSendFailure">
  & Pick<ReturnType<typeof useDesktopChatTurns>, "latestTurnIdsRef" | "markSessionSending" | "isCurrentChatTurn" | "completeChatTurn">
  & Pick<ReturnType<typeof createDesktopSessionSnapshot>, "updateCommittedActiveSession">
  & Pick<ReturnType<typeof createDesktopSessionMessages>, "appendSessionErrorMessage">;
/** Retries the persisted user turn without duplicating its message. */
export function createDesktopChatRetry({
  activeRoleIdRef,
  activeSessionRef,
  sendingSessionsRef,
  reportSendFailure,
  latestTurnIdsRef,
  markSessionSending,
  isCurrentChatTurn,
  completeChatTurn,
  updateCommittedActiveSession,
  appendSessionErrorMessage
}: Args) {
  async function retryFailedChatTurn(errorKey: string): Promise<boolean> {
    const session = activeSessionRef.current;
    const roleId = activeRoleIdRef.current;
    if (!session || !roleId) return false;
    const sessionKey = session.key;
    const target = findChatRetryTarget(session.messages, errorKey);
    if (!target || !canSendSessionState(sendingSessionsRef.current, sessionKey)) return false;
    const errorRow = session.messages.find((message, index) => getChatMessageReactKey(message, index) === errorKey);
    const turnId = window.crypto.randomUUID();
    latestTurnIdsRef.current[sessionKey] = turnId;
    markSessionSending(sessionKey, roleId);
    updateCommittedActiveSession((current) => current?.key === sessionKey
      ? { ...current, messages: current.messages.filter((message, index) => getChatMessageReactKey(message, index) !== errorKey) }
      : current);
    const restoreFailedTurn = (failure: ChatSendFailure) => {
      if (!isCurrentChatTurn(sessionKey, turnId)) return;
      completeChatTurn(sessionKey, turnId);
      if (errorRow) {
        appendSessionErrorMessage(sessionKey, errorRow.content, String(errorRow.metadata?.error_detail ?? ""));
      }
      reportSendFailure(failure);
    };
    try {
      const res = await window.miraDesktop.invoke({
        method: "chat.retry",
        payload: { role_id: roleId, turn_id: turnId, user_message_id: target.userMessageId },
      });
      if (res.error) {
        restoreFailedTurn(res.error);
        return false;
      }
      return true;
    } catch (error) {
      restoreFailedTurn({ message: errorMessage(error, { includeDetail: true }) });
      return false;
    }
  }

  return { retryFailedChatTurn };
}
