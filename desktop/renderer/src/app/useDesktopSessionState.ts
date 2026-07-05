import { useEffect, useRef } from "react";
import { buildOptimisticUserChatMessage, normalizeChatAttachmentPaths } from "../chat/chatComposerState";
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
  NewRoleFormState,
  RoleFormState,
  RoleRecord,
  SessionPayload,
} from "../shared/types";
import type { NavigationEntry } from "./appState";
import type { SettingsSectionId } from "../settings/SettingsSidebar";

type UseDesktopSessionStateArgs = {
  roles: RoleRecord[];
  mainView: AppMainView;
  setRoles: React.Dispatch<React.SetStateAction<RoleRecord[]>>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setActiveSession: React.Dispatch<React.SetStateAction<SessionPayload | null>>;
  setChatReplyTarget: React.Dispatch<React.SetStateAction<ChatReplyTarget | null>>;
  setPendingChatAttachments: React.Dispatch<React.SetStateAction<string[]>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setDraft: React.Dispatch<React.SetStateAction<string>>;
  setUnreadCounts: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  setSelectedAvatarAsset: React.Dispatch<React.SetStateAction<string>>;
  setSelectedChatBackground: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  setSendingSessions: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  chatReplyTarget: ChatReplyTarget | null;
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
  draftRef: React.MutableRefObject<string>;
  pendingChatAttachmentsRef: React.MutableRefObject<string[]>;
  sendingSessionsRef: React.MutableRefObject<Record<string, string>>;
  openRoleRequestIdRef: React.MutableRefObject<number>;
};

/** Owns desktop bridge/session lifecycle so the root app only composes state and actions. */
export function useDesktopSessionState({
  roles,
  mainView,
  setRoles,
  setActiveRoleId,
  setActiveSession,
  setChatReplyTarget,
  setPendingChatAttachments,
  setError,
  setNotice,
  setDraft,
  setUnreadCounts,
  setSelectedAvatarAsset,
  setSelectedChatBackground,
  setActiveIllustration,
  setSendingSessions,
  chatReplyTarget,
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
  draftRef,
  pendingChatAttachmentsRef,
  sendingSessionsRef,
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
    const resolvedSession = mergeIncomingSessionDuringSend(
      activeSessionRef.current,
      nextSession,
      Boolean(nextSession?.key && sendingSessionsRef.current[nextSession.key]),
    );
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
          {
            role: "error",
            content,
            timestamp: new Date().toISOString(),
          },
        ],
      };
    });
  }

  function markSessionSending(sessionKey: string, roleId: string): void {
    if (!sessionKey || !roleId) {
      return;
    }
    setSendingSessions((current) => (
      current[sessionKey] === roleId
        ? current
        : { ...current, [sessionKey]: roleId }
    ));
  }

  function clearSessionSending(sessionKey: string): void {
    if (!sessionKey) {
      return;
    }
    setSendingSessions((current) => {
      if (!current[sessionKey]) {
        return current;
      }
      const next = { ...current };
      delete next[sessionKey];
      return next;
    });
  }

  function clearAllSendingSessions(): void {
    setSendingSessions((current) => (
      Object.keys(current).length ? {} : current
    ));
  }

  async function openRole(
    roleId: string,
    roleOverride: RoleRecord | null = null,
    options?: { recordHistory?: boolean },
  ): Promise<void> {
    const requestId = openRoleRequestIdRef.current + 1;
    openRoleRequestIdRef.current = requestId;
    const switchingRole = activeRoleIdRef.current !== roleId;
    const cachedSession = readCachedRoleSession(roleId);
    const immediateSession = resolveImmediateRoleSession({
      currentRoleId: activeRoleIdRef.current,
      nextRoleId: roleId,
      currentSession: activeSessionRef.current,
      cachedSession,
    });
    if (switchingRole) {
      setChatReplyTarget(null);
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
      return;
    }
    if (!session) {
      setError(sessionError ?? "打开角色会话失败");
      return;
    }
    const latestRoles = await loadRolesFromBridge();
    if (openRoleRequestIdRef.current !== requestId) {
      return;
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
  }

  async function refreshSession(): Promise<void> {
    if (!activeRoleIdRef.current) return;
    await openRole(activeRoleIdRef.current, null, { recordHistory: false });
    setNotice("会话已刷新。");
  }

  async function sendMessage(contentOverride?: string): Promise<void> {
    const draftValue = contentOverride ?? draftRef.current;
    const content = draftValue.trim();
    const media = normalizeChatAttachmentPaths(pendingChatAttachmentsRef.current);
    const currentReplyTarget = chatReplyTarget;
    const roleId = activeRoleIdRef.current;
    const previousSession = activeSessionRef.current;
    const sessionKey = previousSession?.key ?? "";
    if ((!content && media.length === 0) || !roleId || !sessionKey) return;
    if (Object.keys(sendingSessionsRef.current).length > 0) return;
    const persistedReplyTarget = currentReplyTarget;
    markSessionSending(sessionKey, roleId);
    setError("");
    setDraft("");
    draftRef.current = "";
    setChatReplyTarget(null);
    setPendingChatAttachments([]);
    pendingChatAttachmentsRef.current = [];
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
        setDraft(draftValue);
        draftRef.current = draftValue;
        setChatReplyTarget(currentReplyTarget);
        setPendingChatAttachments(media);
        pendingChatAttachmentsRef.current = media;
        setError(res.error.message);
        appendSessionErrorMessage(sessionKey, res.error.message);
        return;
      }
      const nextSession = res.payload.session as SessionPayload;
      cacheRoleSession(roleId, nextSession);
      updateCommittedActiveSession((current) =>
        current?.key === nextSession.key ? nextSession : current,
      );
      clearSessionSending(sessionKey);
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
      setDraft(draftValue);
      draftRef.current = draftValue;
      setChatReplyTarget(currentReplyTarget);
      setPendingChatAttachments(media);
      pendingChatAttachmentsRef.current = media;
      const message = error instanceof Error ? error.message : String(error);
      setError(message);
      appendSessionErrorMessage(sessionKey, message);
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
