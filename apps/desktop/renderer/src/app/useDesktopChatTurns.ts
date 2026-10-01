import { useRef } from "react";
import type { SessionMessage } from "@shiori/plugin-sdk";
import { matchesChatTurn } from "../chat/chatTurnOwnership";
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
  // Retain the latest identity after completion so delayed persistence acknowledgements
  // can reconcile; sendingSessions determines whether that turn is still active.
  const latestTurnIdsRef = useRef<Record<string, string>>({});

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

  function isLatestChatTurn(sessionKey: string, turnId: string): boolean {
    return matchesChatTurn(latestTurnIdsRef.current, sessionKey, turnId);
  }

  function isCurrentChatTurn(sessionKey: string, turnId: string): boolean {
    return isLatestChatTurn(sessionKey, turnId) && Boolean(sendingSessionsRef.current[sessionKey]);
  }

  function isChatTurnCancelling(sessionKey: string, turnId: string): boolean {
    return isCurrentChatTurn(sessionKey, turnId)
      && Boolean(cancellingSessionsRef.current[sessionKey]);
  }

  function completeChatTurn(sessionKey: string, turnId: string): void {
    if (!isCurrentChatTurn(sessionKey, turnId)) return;
    clearSessionCancelling(sessionKey);
    clearSessionSending(sessionKey);
  }

  function clearAllSendingSessions(): void {
    pendingUserMessagesRef.current = {};
    latestTurnIdsRef.current = {};
    sendingSessionsRef.current = clearAllSendingSessionsState(sendingSessionsRef.current);
    setSendingSessions((current) => clearAllSendingSessionsState(current));
    cancellingSessionsRef.current = {};
    setCancellingSessions((current) => clearAllSendingSessionsState(current));
  }

  return { pendingUserMessagesRef, latestTurnIdsRef, markSessionSending, clearSessionSending, markSessionCancelling, clearSessionCancelling, isLatestChatTurn, isCurrentChatTurn, isChatTurnCancelling, completeChatTurn, clearAllSendingSessions };
}
