import { useLatestRef } from "@shiori/plugin-sdk";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import { fetchRoleSession } from "./desktopSessionProtocol";
import { createDesktopSessionCache } from "./desktopSessionCache";
import { createDesktopSessionSnapshot } from "./desktopSessionSnapshot";
import { createDesktopSessionMessages } from "./desktopSessionMessages";
import { createDesktopRoleList } from "./desktopRoleList";
import { createDesktopRoleNavigation } from "./desktopRoleNavigation";
import { createDesktopChatSend } from "./desktopChatSend";
import { createDesktopChatRetry } from "./desktopChatRetry";
import { createDesktopChatCancellation } from "./desktopChatCancellation";
import { useDesktopChatTurns } from "./useDesktopChatTurns";
import { useDesktopSessionPagination } from "./useDesktopSessionPagination";

/** Composes session cache, navigation, pagination and chat-turn owners. */
export function useDesktopSessionState(args: DesktopSessionStateArgs) {
  const latestCallbacks = useLatestRef({
    applyRoleSnapshot: args.applyRoleSnapshot,
    buildNavigationEntry: args.buildNavigationEntry,
    pushNavigationEntry: args.pushNavigationEntry,
    replaceNavigationEntry: args.replaceNavigationEntry,
  });
  const cache = createDesktopSessionCache(args);
  const turns = useDesktopChatTurns(args);
  const snapshot = createDesktopSessionSnapshot({ ...args, ...cache, ...turns });
  const messages = createDesktopSessionMessages({ ...args, ...cache, ...turns, ...snapshot });
  const pagination = useDesktopSessionPagination({
    ...args,
    reportError: args.feedback.error,
    updateCommittedActiveSession: snapshot.updateCommittedActiveSession,
  });
  const roleList = createDesktopRoleList({ ...args, ...cache });
  const navigation = createDesktopRoleNavigation({
    ...args, ...cache, ...snapshot, ...pagination, ...roleList, latestCallbacks,
  });
  const send = createDesktopChatSend({ ...args, ...cache, ...turns, ...snapshot, ...messages });
  const retry = createDesktopChatRetry({ ...args, ...turns, ...snapshot, ...messages });
  const cancellation = createDesktopChatCancellation({ ...args, ...turns, ...snapshot, ...messages });

  return {
    cacheRoleSession: cache.cacheRoleSession,
    removeCachedRoleSession: cache.removeCachedRoleSession,
    ...roleList,
    fetchRoleSession,
    loadOlderMessages: pagination.loadOlderMessages,
    loadMessagesAround: pagination.loadMessagesAround,
    ...navigation,
    clearAllSendingSessions: turns.clearAllSendingSessions,
    clearSessionSending: turns.clearSessionSending,
    isCurrentChatTurn: turns.isCurrentChatTurn,
    isChatTurnCancelling: turns.isChatTurnCancelling,
    completeChatTurn: turns.completeChatTurn,
    ...snapshot,
    appendSessionErrorMessage: messages.appendSessionErrorMessage,
    ...send,
    ...retry,
    ...cancellation,
  };
}
