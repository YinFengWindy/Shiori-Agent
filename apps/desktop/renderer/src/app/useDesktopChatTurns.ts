import { useRef } from "react";
import type { SessionMessage } from "@shiori/plugin-sdk";
import { isActiveChatTurn } from "../chat/chatTurnOwnership";
import { markSendingSessionState, clearSendingSessionState, clearAllSendingSessionsState } from "./desktopSendingSessions";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
type Args = Pick<DesktopSessionStateArgs, "sendingSessionsRef" | "cancellingSessionsRef" | "setSendingSessions" | "setCancellingSessions">;
/** Tracks sending, cancellation and terminal ownership for concurrent role turns. */
export function useDesktopChatTurns({
  sendingSessionsRef,
  cancellingSessionsRef,
  setSendingSessions,
  setCancellingSessions
}: Args) {
  const pendingUserMessagesRef = useRef<Record<string, SessionMessage>>({});
  const activeTurnIdsRef = useRef<Record<string, string>>({});

  function markSessionSending(sessionKey: string, roleId: string): void {
    sendingSessionsRef.current = markSendingSessionState(sendingSessionsRef.current, sessionKey, roleId);
    setSendingSessions((current) => markSendingSessionState(current, sessionKey, roleId));
  }

  function clearSessionSending(sessionKey: string): void {
    sendingSessionsRef.current = clearSendingSessionState(sendingSessionsRef.current, sessionKey);
    setSendingSessions((current) => clearSendingSessionState(current, sessionKey));
  }

  function markSessionCancelling(sessionKey: string, roleId: string): void {
    cancellingSessionsRef.current = { ...cancellingSessionsRef.current, [sessionKey]: roleId };
    setCancellingSessions((current) => current[sessionKey] === roleId ? current : { ...current, [sessionKey]: roleId });
  }

  function clearSessionCancelling(sessionKey: string): void {
    if (!cancellingSessionsRef.current[sessionKey]) return;
    const next = { ...cancellingSessionsRef.current };
    delete next[sessionKey];
    cancellingSessionsRef.current = next;
    setCancellingSessions((current) => {
      if (!current[sessionKey]) return current;
      const updated = { ...current };
      delete updated[sessionKey];
      return updated;
    });
  }

  function isCurrentChatTurn(sessionKey: string, turnId: string): boolean {
    return isActiveChatTurn(activeTurnIdsRef.current, sessionKey, turnId);
  }

  function isChatTurnCancelling(sessionKey: string, turnId: string): boolean {
    return isCurrentChatTurn(sessionKey, turnId)
      && Boolean(cancellingSessionsRef.current[sessionKey]);
  }

  function completeChatTurn(sessionKey: string, turnId: string): void {
    if (!isCurrentChatTurn(sessionKey, turnId)) return;
    delete activeTurnIdsRef.current[sessionKey];
    clearSessionCancelling(sessionKey);
    clearSessionSending(sessionKey);
  }

  function clearAllSendingSessions(): void {
    pendingUserMessagesRef.current = {};
    activeTurnIdsRef.current = {};
    sendingSessionsRef.current = clearAllSendingSessionsState(sendingSessionsRef.current);
    setSendingSessions((current) => clearAllSendingSessionsState(current));
    cancellingSessionsRef.current = {};
    setCancellingSessions((current) => clearAllSendingSessionsState(current));
  }

  return { pendingUserMessagesRef, activeTurnIdsRef, markSessionSending, clearSessionSending, markSessionCancelling, clearSessionCancelling, isCurrentChatTurn, isChatTurnCancelling, completeChatTurn, clearAllSendingSessions };
}
