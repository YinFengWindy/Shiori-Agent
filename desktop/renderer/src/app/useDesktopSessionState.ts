import { startTransition, useEffect, useRef } from "react";
import { buildOptimisticUserChatMessage, normalizeChatAttachmentPaths } from "../chat/chatComposerState";
import {
  readRoleSessionCache,
  removeRoleSessionCache,
  resolveImmediateRoleSession,
  retainRoleSessionCache,
  writeRoleSessionCache,
  type RoleSessionCache,
} from "../chat/roleSessionCache";
import { isProactiveAssistantMessage, getRoleIdFromSession } from "./appState";
import { reconcileRoles } from "../roles/roleListState";
import type {
  AppMainView,
  ChatReplyTarget,
  EventLog,
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
  activeRoleId: string;
  activeIllustration: string;
  setHealth: React.Dispatch<React.SetStateAction<string>>;
  setRoles: React.Dispatch<React.SetStateAction<RoleRecord[]>>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setActiveSession: React.Dispatch<React.SetStateAction<SessionPayload | null>>;
  setChatReplyTarget: React.Dispatch<React.SetStateAction<ChatReplyTarget | null>>;
  setPendingChatAttachments: React.Dispatch<React.SetStateAction<string[]>>;
  setEvents: React.Dispatch<React.SetStateAction<EventLog[]>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setDraft: React.Dispatch<React.SetStateAction<string>>;
  setUnreadCounts: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  setSelectedAvatarAsset: React.Dispatch<React.SetStateAction<string>>;
  setSelectedChatBackground: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  setWindowMaximized: React.Dispatch<React.SetStateAction<boolean>>;
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
  activeRoleId,
  activeIllustration,
  setHealth,
  setRoles,
  setActiveRoleId,
  setActiveSession,
  setChatReplyTarget,
  setPendingChatAttachments,
  setEvents,
  setError,
  setNotice,
  setDraft,
  setUnreadCounts,
  setSelectedAvatarAsset,
  setSelectedChatBackground,
  setActiveIllustration,
  setWindowMaximized,
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
    activeSessionRef.current = nextSession;
    if (nextSession) {
      const roleId = getRoleIdFromSession(nextSession) || activeRoleIdRef.current;
      if (roleId) {
        cacheRoleSession(roleId, nextSession);
      }
    }
    setActiveSession(nextSession);
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

  async function refreshBridge(): Promise<void> {
    setError("");
    setHealth("connecting");
    const res = await window.miraDesktop.invoke({
      method: "health",
      payload: {},
    });
    if (res.error) {
      setHealth("offline");
      setError(res.error.message);
      return;
    }
    setHealth("online");
    const nextRoles = await loadRolesFromBridge();
    if (!nextRoles) {
      return;
    }
    const currentRoleId = activeRoleIdRef.current;
    if (currentRoleId) {
      const activeRole = nextRoles.find((item) => item.id === currentRoleId) ?? null;
      if (activeRole) {
        await openRole(activeRole.id, activeRole, { recordHistory: false });
      } else if (nextRoles[0]) {
        await openRole(nextRoles[0].id, nextRoles[0], { recordHistory: false });
      } else {
        setActiveRoleId("");
        commitActiveSession(null);
        setActiveIllustration("");
      }
    } else if (nextRoles[0]) {
      await openRole(nextRoles[0].id, nextRoles[0], { recordHistory: false });
    }
    setNotice("连接桥已刷新。");
  }

  async function restartBridge(): Promise<void> {
    setError("");
    setHealth("connecting");
    const result = await window.miraDesktop.restartBridge();
    if (!result.ok) {
      setHealth("offline");
      setError(result.lastError || "连接桥重启失败");
      return;
    }
    setNotice("连接桥已重启。");
    await refreshBridge();
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

  useEffect(() => {
    const savedRoleId = window.localStorage.getItem("miraDesktop.activeRoleId") ?? "";
    const savedIllustration = window.localStorage.getItem("miraDesktop.activeIllustration") ?? "";
    if (savedRoleId) {
      setActiveRoleId(savedRoleId);
    }
    if (savedIllustration) {
      setActiveIllustration(savedIllustration);
    }
  }, [setActiveRoleId, setActiveIllustration]);

  useEffect(() => {
    if (activeRoleId) {
      window.localStorage.setItem("miraDesktop.activeRoleId", activeRoleId);
    } else {
      window.localStorage.removeItem("miraDesktop.activeRoleId");
    }
    activeRoleIdRef.current = activeRoleId;
  }, [activeRoleId, activeRoleIdRef]);

  useEffect(() => {
    if (activeIllustration) {
      window.localStorage.setItem("miraDesktop.activeIllustration", activeIllustration);
    } else {
      window.localStorage.removeItem("miraDesktop.activeIllustration");
    }
  }, [activeIllustration]);

  useEffect(() => {
    const off = window.miraDesktop.onEvent((event) => {
      startTransition(() => {
        setEvents((items) => [...items, { method: event.method, payload: event.payload }].slice(-12));
        if (event.method === "window.state") {
          setWindowMaximized(Boolean(event.payload.isMaximized));
          return;
        }

        if (event.method === "bridge.exit") {
          clearAllSendingSessions();
          setHealth("offline");
          setError(String(event.payload.message ?? "bridge exited"));
          setNotice("连接桥已停止。你可以刷新或重启它。");
          return;
        }

        if (event.method === "session.updated") {
          const session = event.payload.session as SessionPayload | undefined;
          if (!session) return;
          const currentSession = activeSessionRef.current;
          const currentView = mainViewRef.current;
          const roleId = getRoleIdFromSession(session);
          const isActiveSession = currentSession?.key === session.key;
          const isVisibleChat = isActiveSession && currentView.kind === "chat";
          if (roleId) {
            cacheRoleSession(roleId, session);
          }
          if (isActiveSession) {
            commitActiveSession(session);
            const currentRole = rolesRef.current.find((item) => item.id === activeRoleIdRef.current) ?? null;
            setActiveIllustration((current) =>
              chooseIllustrationRef.current(currentRole, session, current),
            );
          }
          if (event.id === "proactive" && roleId && isProactiveAssistantMessage(session) && !isVisibleChat) {
            setUnreadCounts((current) => ({
              ...current,
              [roleId]: (current[roleId] ?? 0) + 1,
            }));
          }
          return;
        }

        const eventSessionKey = String(event.payload.session_key ?? "");

        if (event.method === "chat.delta") {
          const currentSession = activeSessionRef.current;
          if (!currentSession || eventSessionKey !== currentSession.key) return;
          const delta = String(event.payload.content_delta ?? "");
          if (!delta) return;
          updateCommittedActiveSession((current) => {
            if (!current) return current;
            const messages = [...current.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "assistant" && !last.id) {
              last.content += delta;
            } else {
              messages.push({ role: "assistant", content: delta });
            }
            return { ...current, messages };
          });
          return;
        }

        if (event.method === "chat.done") {
          clearSessionSending(eventSessionKey);
          return;
        }

        if (event.method === "chat.error") {
          clearSessionSending(eventSessionKey);
          const currentSession = activeSessionRef.current;
          if (!currentSession || eventSessionKey !== currentSession.key) return;
          const message = String(event.payload.message ?? "对话失败");
          setError(message);
          appendSessionErrorMessage(currentSession.key, message);
        }
      });
    });
    return off;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      const currentWindowState = await window.miraDesktop.windowState();
      if (cancelled) return;
      setWindowMaximized(currentWindowState.isMaximized);

      const bridgeStatus = await window.miraDesktop.bridgeStatus();
      if (cancelled) return;
      if (!bridgeStatus.running && bridgeStatus.lastError) {
        setHealth("offline");
        setError(bridgeStatus.lastError);
        return;
      }
      const healthRes = await window.miraDesktop.invoke({
        method: "health",
        payload: {},
      });
      if (cancelled) return;
      if (healthRes.error) {
        setHealth("offline");
        setError(healthRes.error.message);
        return;
      }
      setHealth("online");
      setError("");

      const nextRoles = await loadRolesFromBridge();
      if (cancelled || !nextRoles) {
        return;
      }
      const preferredRoleId =
        nextRoles.find((item) => item.id === activeRoleIdRef.current)?.id
        ?? nextRoles.find((item) => item.id === window.localStorage.getItem("miraDesktop.activeRoleId"))?.id
        ?? nextRoles[0]?.id;
      if (preferredRoleId) {
        const preferredRole = nextRoles.find((item) => item.id === preferredRoleId) ?? null;
        void openRole(preferredRoleId, preferredRole, { recordHistory: false });
      }
      pushNavigationEntryRef.current(buildNavigationEntryRef.current({ kind: "chat" }, preferredRoleId ?? ""));
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    cacheRoleSession,
    removeCachedRoleSession,
    loadRolesFromBridge,
    fetchRoleSession,
    refreshSession,
    refreshBridge,
    restartBridge,
    openRole,
    sendMessage,
    commitActiveSession,
    updateCommittedActiveSession,
  };
}
