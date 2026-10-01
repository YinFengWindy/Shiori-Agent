import type { SessionMessageUpdatePayload } from "@shiori/sdk";
import { ensureChatMessageRenderId } from "../chat/chatMessageIdentity";
import { mergeSessionSummaryAndMessage } from "./sessionMessagePagination";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import type { useDesktopChatTurns } from "./useDesktopChatTurns";
import type { createDesktopSessionSnapshot } from "./desktopSessionSnapshot";
import type { createDesktopSessionCache } from "./desktopSessionCache";

type Args = Pick<DesktopSessionStateArgs, "activeSessionRef">
  & Pick<ReturnType<typeof useDesktopChatTurns>, "pendingUserMessagesRef">
  & ReturnType<typeof createDesktopSessionSnapshot>
  & Pick<ReturnType<typeof createDesktopSessionCache>, "cacheRoleSession" | "readCachedRoleSession">;

/** Applies turn messages to their owning role without navigating away from the visible role. */
export function createDesktopSessionMessages({
  activeSessionRef, pendingUserMessagesRef, commitActiveSession,
  updateCommittedActiveSession, cacheRoleSession, readCachedRoleSession,
}: Args) {
  function commitSessionMessageUpdate(roleId: string, update: SessionMessageUpdatePayload) {
    const visible = activeSessionRef.current?.key === update.session.key;
    const current = visible ? activeSessionRef.current : readCachedRoleSession(roleId);
    const next = mergeSessionSummaryAndMessage(current, update.session, update.message, update.messages);
    if (visible) commitActiveSession(next);
    else cacheRoleSession(roleId, next);
  }

  function appendSessionErrorMessage(sessionKey: string, message: string, detail = ""): void {
    const content = message.trim();
    if (!content) return;
    delete pendingUserMessagesRef.current[sessionKey];
    const errorDetail = detail.trim();
    updateCommittedActiveSession((current) => {
      if (!current || current.key !== sessionKey) return current;
      return {
        ...current,
        messages: [
          ...current.messages,
          ensureChatMessageRenderId({
            role: "error",
            content,
            timestamp: new Date().toISOString(),
            ...(errorDetail ? { metadata: { error_detail: errorDetail } } : {}),
          }),
        ],
      };
    });
  }

  return { commitSessionMessageUpdate, appendSessionErrorMessage };
}
