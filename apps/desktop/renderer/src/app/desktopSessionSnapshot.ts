import type { SessionPayload } from "@shiori/plugin-sdk";
import { mergeIncomingSessionDuringSend, shouldClearPendingUserMessage } from "../chat/chatSessionMerge";
import { reconcileSessionMessageRenderIds } from "../chat/chatMessageIdentity";
import { getRoleIdFromSession } from "./appState";
import { mergeOpenedSessionSnapshot } from "./sessionMessagePagination";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import type { useDesktopChatTurns } from "./useDesktopChatTurns";
import type { createDesktopSessionCache } from "./desktopSessionCache";
type Args = Pick<DesktopSessionStateArgs, "activeSessionRef" | "activeRoleIdRef" | "sendingSessionsRef" | "setActiveSession">
  & Pick<ReturnType<typeof useDesktopChatTurns>, "pendingUserMessagesRef">
  & Pick<ReturnType<typeof createDesktopSessionCache>, "cacheRoleSession">;
/** Reconciles snapshots with pending user messages and stable render identities. */
export function createDesktopSessionSnapshot({
  activeSessionRef,
  activeRoleIdRef,
  sendingSessionsRef,
  setActiveSession,
  pendingUserMessagesRef,
  cacheRoleSession
}: Args) {
  function commitActiveSession(nextSession: SessionPayload | null): void {
    const incomingSession = nextSession
      ? mergeOpenedSessionSnapshot(activeSessionRef.current, nextSession)
      : null;
    const pendingUserMessage = incomingSession
      ? pendingUserMessagesRef.current[incomingSession.key] ?? null
      : null;
    const sending = Boolean(incomingSession?.key && sendingSessionsRef.current[incomingSession.key]);
    const mergedSession = mergeIncomingSessionDuringSend(
      activeSessionRef.current,
      incomingSession,
      sending,
      pendingUserMessage,
    );
    if (
      pendingUserMessage
      && incomingSession
      && shouldClearPendingUserMessage(pendingUserMessage, incomingSession, sending)
    ) {
      delete pendingUserMessagesRef.current[incomingSession.key];
    }
    const resolvedSession = reconcileSessionMessageRenderIds(activeSessionRef.current, mergedSession);
    activeSessionRef.current = resolvedSession;
    if (resolvedSession) {
      const roleId = getRoleIdFromSession(resolvedSession) || activeRoleIdRef.current;
      if (roleId) {
        cacheRoleSession(roleId, resolvedSession);
      }
    }
    setActiveSession(resolvedSession);
  }

  function updateCommittedActiveSession(
    updater: (current: SessionPayload | null) => SessionPayload | null,
  ): void {
    const nextSession = updater(activeSessionRef.current);
    activeSessionRef.current = nextSession;
    if (nextSession) {
      const roleId = getRoleIdFromSession(nextSession) || activeRoleIdRef.current;
      if (roleId) {
        cacheRoleSession(roleId, nextSession);
      }
    }
    setActiveSession(nextSession);
  }


  return { commitActiveSession, updateCommittedActiveSession };
}
