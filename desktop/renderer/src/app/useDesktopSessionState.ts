import { useEffect, useRef } from "react";
import { buildOptimisticUserChatMessage, normalizeChatAttachmentPaths } from "../chat/chatComposerState";
import { ensureChatMessageRenderId, reconcileSessionMessageRenderIds } from "../chat/chatMessageIdentity";
import { mergeIncomingSessionDuringSend } from "../chat/chatSessionMerge";
import {
  readRoleSessionCache,
  removeRoleSessionCache,
  resolveImmediateRoleSession,
  retainRoleSessionCache,
  writeRoleSessionCache,
  type RoleSessionCache,
} from "../chat/roleSessionCache";
import { getRoleIdFromSession } from "./appState";
import { reconcileRoles } from "../roles/roleListState";
import type {
  AppMainView,
  ChatReplyTarget,
  ChatSendRequest,
  NewRoleFormState,
  RoleFormState,
  RoleRecord,
  SessionPayload,
} from "../shared/types";
import type { NavigationEntry } from "./appState";
import type { SettingsSectionId } from "../settings/SettingsSidebar";

type SendingSessionsMap = Record<string, string>;

type UseDesktopSessionStateArgs = {
  roles: RoleRecord[];
  mainView: AppMainView;
  setRoles: React.Dispatch<React.SetStateAction<RoleRecord[]>>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setActiveSession: React.Dispatch<React.SetStateAction<SessionPayload | null>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setUnreadCounts: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  setSelectedAvatarAsset: React.Dispatch<React.SetStateAction<string>>;
  setSelectedChatBackground: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  setSendingSessions: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  chooseIllustration: (
    role: RoleRecord | null,
    session: SessionPayload | null,
    fallbackIllustration: string,
  ) => string;
  applyRoleSnapshot: (role: RoleRecord, sessionOverride?: SessionPayload | null) => void;
  buildNavigationEntry: (
    view: AppMainView,
    roleId?: string,
    section?: SettingsSectionId,
  ) => NavigationEntry;
  pushNavigationEntry: (entry: NavigationEntry) => void;
  replaceNavigationEntry: (entry: NavigationEntry) => void;
  activeRoleIdRef: React.MutableRefObject<string>;
  activeSessionRef: React.MutableRefObject<SessionPayload | null>;
  roleSessionCacheRef: React.MutableRefObject<RoleSessionCache>;
  mainViewRef: React.MutableRefObject<AppMainView>;
  rolesRef: React.MutableRefObject<RoleRecord[]>;
  sendingSessionsRef: React.MutableRefObject<Record<string, string>>;
  unreadCountsRef: React.MutableRefObject<Record<string, number>>;
  openRoleRequestIdRef: React.MutableRefObject<number>;
};

/** Marks a chat session as sending while preserving the previous object when nothing changed. */
export function markSendingSessionState(
  current: SendingSessionsMap,
  sessionKey: string,
  roleId: string,
): SendingSessionsMap {
  if (!sessionKey || !roleId || current[sessionKey] === roleId) {
    return current;
  }
  return {
    ...current,
    [sessionKey]: roleId,
  };
}

/** Clears one in-flight chat session while preserving the previous object when it was already absent. */
export function clearSendingSessionState(
  current: SendingSessionsMap,
  sessionKey: string,
): SendingSessionsMap {
  if (!sessionKey || !current[sessionKey]) {
    return current;
  }
  const next = { ...current };
  delete next[sessionKey];
  return next;
}

/** Clears every in-flight chat session while preserving the previous object when already empty. */
export function clearAllSendingSessionsState(current: SendingSessionsMap): SendingSessionsMap {
  return Object.keys(current).length ? {} : current;
}

/** Returns whether the current session can send without being blocked by another role's in-flight turn. */
export function canSendSessionState(current: SendingSessionsMap, sessionKey: string): boolean {
  return Boolean(sessionKey) && !current[sessionKey];
}

/** Owns desktop bridge/session lifecycle so the root app only composes state and actions. */
export function useDesktopSessionState({
  roles,
  mainView,
  setRoles,
  setActiveRoleId,
  setActiveSession,
  setError,
  setNotice,
  setUnreadCounts,
  setSelectedAvatarAsset,
  setSelectedChatBackground,
  setActiveIllustration,
  setSendingSessions,
  chooseIllustration,
  applyRoleSnapshot,
  buildNavigationEntry,
  pushNavigationEntry,
  replaceNavigationEntry,
  activeRoleIdRef,
  activeSessionRef,
  roleSessionCacheRef,
  mainViewRef,
  rolesRef,
  sendingSessionsRef,
  unreadCountsRef,
  openRoleRequestIdRef,
}: UseDesktopSessionStateArgs) {
  const chooseIllustrationRef = useRef(chooseIllustration);
  const buildNavigationEntryRef = useRef(buildNavigationEntry);
  const pushNavigationEntryRef = useRef(pushNavigationEntry);
  const replaceNavigationEntryRef = useRef(replaceNavigationEntry);
  const applyRoleSnapshotRef = useRef(applyRoleSnapshot);

  useEffect(() => {
    chooseIllustrationRef.current = chooseIllustration;
    buildNavigationEntryRef.current = buildNavigationEntry;
    pushNavigationEntryRef.current = pushNavigationEntry;
    replaceNavigationEntryRef.current = replaceNavigationEntry;
    applyRoleSnapshotRef.current = applyRoleSnapshot;
  }, [chooseIllustration, buildNavigationEntry, pushNavigationEntry, replaceNavigationEntry, applyRoleSnapshot]);

  function cacheRoleSession(roleId: string, session: SessionPayload): void {
    roleSessionCacheRef.current = writeRoleSessionCache(roleSessionCacheRef.current, roleId, session);
  }

  function readCachedRoleSession(roleId: string): SessionPayload | null {
    return readRoleSessionCache(roleSessionCacheRef.current, roleId);
  }

  function removeCachedRoleSession(roleId: string): void {
    roleSessionCacheRef.current = removeRoleSessionCache(roleSessionCacheRef.current, roleId);
  }

  function retainCachedRoleSessions(nextRoles: readonly RoleRecord[]): void {
    roleSessionCacheRef.current = retainRoleSessionCache(
      roleSessionCacheRef.current,
      nextRoles.map((role) => role.id),
    );
  }

  function commitActiveSession(nextSession: SessionPayload | null): void {
    const mergedSession = mergeIncomingSessionDuringSend(
      activeSessionRef.current,
      nextSession,
      Boolean(nextSession?.key && sendingSessionsRef.current[nextSession.key]),
    );
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
    setActiveSession((current) => {
      const nextSession = updater(current);
      activeSessionRef.current = nextSession;
      if (nextSession) {
        const roleId = getRoleIdFromSession(nextSession) || activeRoleIdRef.current;
        if (roleId) {
          cacheRoleSession(roleId, nextSession);
        }
      }
      return nextSession;
    });
  }

  async function loadRolesFromBridge(): Promise<RoleRecord[] | null> {
    const rolesRes = await window.miraDesktop.invoke({
      method: "roles.list",
      payload: {},
    });
    if (rolesRes.error) {
      setError(rolesRes.error.message);
      return null;
    }
    const nextRoles = (rolesRes.payload.roles as RoleRecord[]) ?? [];
    let mergedRoles = nextRoles;
    setRoles((current) => {
      mergedRoles = reconcileRoles(current, nextRoles);
      return mergedRoles;
    });
    setUnreadCounts((current) => {
      const next: Record<string, number> = {};
      nextRoles.forEach((role) => {
        if (current[role.id]) {
          next[role.id] = current[role.id];
        }
      });
      return next;
    });
    retainCachedRoleSessions(nextRoles);
    return mergedRoles;
  }

  /** Loads the authoritative session for a role without mutating renderer state. */
  async function fetchRoleSession(roleId: string): Promise<{
    error: string | null;
    session: SessionPayload | null;
  }> {
    try {
      const res = await window.miraDesktop.invoke({
        method: "session.openByRole",
        payload: { role_id: roleId },
      });
      if (res.error) {
        return {
          error: res.error.message,
          session: null,
        };
      }
      return {
        error: null,
        session: res.payload.session as SessionPayload,
      };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : String(error),
        session: null,
      };
    }
  }

  function appendSessionErrorMessage(sessionKey: string, message: string): void {
    const content = message.trim();
    if (!content) return;
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
          }),
        ],
      };
    });
  }

  function markSessionSending(sessionKey: string, roleId: string): void {
    sendingSessionsRef.current = markSendingSessionState(sendingSessionsRef.current, sessionKey, roleId);
    setSendingSessions((current) => markSendingSessionState(current, sessionKey, roleId));
  }

  function clearSessionSending(sessionKey: string): void {
    sendingSessionsRef.current = clearSendingSessionState(sendingSessionsRef.current, sessionKey);
    setSendingSessions((current) => clearSendingSessionState(current, sessionKey));
  }

  function clearAllSendingSessions(): void {
    sendingSessionsRef.current = clearAllSendingSessionsState(sendingSessionsRef.current);
    setSendingSessions((current) => clearAllSendingSessionsState(current));
  }

  async function openRole(
    roleId: string,
    roleOverride: RoleRecord | null = null,
    options?: { recordHistory?: boolean },
  ): Promise<boolean> {
    const requestId = openRoleRequestIdRef.current + 1;
    openRoleRequestIdRef.current = requestId;
    const previousRoleId = activeRoleIdRef.current;
    const previousSession = activeSessionRef.current;
    const previousRole = previousRoleId
      ? rolesRef.current.find((item) => item.id === previousRoleId) ?? null
      : null;
    const switchingRole = activeRoleIdRef.current !== roleId;
    const previousUnreadCount = unreadCountsRef.current[roleId] ?? 0;
    const cachedSession = readCachedRoleSession(roleId);
    const immediateSession = resolveImmediateRoleSession({
      currentRoleId: activeRoleIdRef.current,
      nextRoleId: roleId,
      currentSession: activeSessionRef.current,
      cachedSession,
    });
    if (switchingRole) {
    }
    const role = roleOverride ?? rolesRef.current.find((item) => item.id === roleId) ?? null;
    if (role) {
      applyRoleSnapshotRef.current(role, cachedSession);
      setError("");
    }
    if (immediateSession !== activeSessionRef.current) {
      commitActiveSession(immediateSession);
    }
    const { error: sessionError, session } = await fetchRoleSession(roleId);
    if (openRoleRequestIdRef.current !== requestId) {
      return false;
    }
    if (!session) {
      if (switchingRole) {
        if (previousRole) {
          applyRoleSnapshotRef.current(previousRole, previousSession);
        } else {
          setActiveRoleId(previousRoleId);
          activeRoleIdRef.current = previousRoleId;
          setActiveIllustration("");
          setSelectedAvatarAsset("");
          setSelectedChatBackground("");
        }
        commitActiveSession(previousSession);
        if (previousUnreadCount > 0) {
          setUnreadCounts((current) => (
            current[roleId] === previousUnreadCount
              ? current
              : {
                  ...current,
                  [roleId]: previousUnreadCount,
                }
          ));
        }
      }
      setError(sessionError ?? "打开角色会话失败");
      return false;
    }
    const latestRoles = await loadRolesFromBridge();
    if (openRoleRequestIdRef.current !== requestId) {
      return false;
    }
    cacheRoleSession(roleId, session);
    setActiveRoleId(roleId);
    commitActiveSession(session);
    setError("");
    const resolvedRole = roleOverride
      ?? latestRoles?.find((item) => item.id === roleId)
      ?? rolesRef.current.find((item) => item.id === roleId)
      ?? null;
    if (resolvedRole) {
      applyRoleSnapshotRef.current(resolvedRole, session);
    } else {
      setActiveIllustration("");
      setSelectedAvatarAsset("");
      setSelectedChatBackground("");
    }
    if (options?.recordHistory !== false) {
      pushNavigationEntryRef.current(buildNavigationEntryRef.current({ kind: "chat" }, roleId));
    } else if (mainViewRef.current.kind === "chat") {
      replaceNavigationEntryRef.current(buildNavigationEntryRef.current({ kind: "chat" }, roleId));
    }
    return true;
  }

  async function refreshSession(): Promise<void> {
    if (!activeRoleIdRef.current) return;
    const refreshed = await openRole(activeRoleIdRef.current, null, { recordHistory: false });
    if (refreshed) {
      setNotice("会话已刷新。");
    }
  }

  async function sendMessage(request: ChatSendRequest): Promise<boolean> {
    const content = request.content.trim();
    const media = normalizeChatAttachmentPaths(request.attachments);
    const currentReplyTarget = request.replyTarget;
    const roleId = activeRoleIdRef.current;
    const previousSession = activeSessionRef.current;
    const sessionKey = previousSession?.key ?? "";
    if ((!content && media.length === 0) || !roleId || !sessionKey) return false;
    if (!canSendSessionState(sendingSessionsRef.current, sessionKey)) return false;
    const persistedReplyTarget = currentReplyTarget;
    markSessionSending(sessionKey, roleId);
    setError("");
    updateCommittedActiveSession((current) =>
      current?.key === sessionKey
        ? {
            ...current,
            messages: [...current.messages, buildOptimisticUserChatMessage(content, media, persistedReplyTarget)],
          }
        : current,
    );
    try {
      const res = await window.miraDesktop.invoke({
        method: "chat.send",
        payload: {
          role_id: roleId,
          content,
          media,
          reply_to_message_id: persistedReplyTarget?.messageId ?? "",
          reply_to_content: persistedReplyTarget?.content ?? "",
          reply_to_sender: persistedReplyTarget?.sender ?? "",
        },
      });
      if (res.error) {
        clearSessionSending(sessionKey);
        const { session: recoveredSession } = await fetchRoleSession(roleId);
        if (recoveredSession) {
          cacheRoleSession(roleId, recoveredSession);
          updateCommittedActiveSession((current) =>
            current?.key === sessionKey ? recoveredSession : current,
          );
        } else if (previousSession) {
          updateCommittedActiveSession((current) =>
            current?.key === sessionKey ? previousSession : current,
          );
        }
        setError(res.error.message);
        appendSessionErrorMessage(sessionKey, res.error.message);
        return false;
      }
      const nextSession = res.payload.session as SessionPayload;
      // Keep the optimistic user turn visible when chat.send resolves with a stale session snapshot.
      commitActiveSession(nextSession);
      return true;
    } catch (error) {
      clearSessionSending(sessionKey);
      const { session: recoveredSession } = await fetchRoleSession(roleId);
      if (recoveredSession) {
        cacheRoleSession(roleId, recoveredSession);
        updateCommittedActiveSession((current) =>
          current?.key === sessionKey ? recoveredSession : current,
        );
      } else if (previousSession) {
        updateCommittedActiveSession((current) =>
          current?.key === sessionKey ? previousSession : current,
        );
      }
      const message = error instanceof Error ? error.message : String(error);
      setError(message);
      appendSessionErrorMessage(sessionKey, message);
      return false;
    }
  }

  return {
    cacheRoleSession,
    removeCachedRoleSession,
    loadRolesFromBridge,
    fetchRoleSession,
    refreshSession,
    clearAllSendingSessions,
    clearSessionSending,
    appendSessionErrorMessage,
    openRole,
    sendMessage,
    commitActiveSession,
    updateCommittedActiveSession,
  };
}
