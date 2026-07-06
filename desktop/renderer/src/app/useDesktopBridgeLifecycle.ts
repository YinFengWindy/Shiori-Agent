import { startTransition, useEffect } from "react";
import { getRoleIdFromSession, isProactiveAssistantMessage, type NavigationEntry } from "./appState";
import type { EventLog, RoleRecord, SessionPayload, AppMainView } from "../shared/types";

type UseDesktopBridgeLifecycleArgs = {
  activeRoleId: string;
  activeIllustration: string;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  setHealth: React.Dispatch<React.SetStateAction<string>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setEvents: React.Dispatch<React.SetStateAction<EventLog[]>>;
  setWindowMaximized: React.Dispatch<React.SetStateAction<boolean>>;
  setUnreadCounts: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  activeRoleIdRef: React.MutableRefObject<string>;
  activeSessionRef: React.MutableRefObject<SessionPayload | null>;
  mainViewRef: React.MutableRefObject<AppMainView>;
  rolesRef: React.MutableRefObject<RoleRecord[]>;
  chooseIllustration: (role: RoleRecord | null, session: SessionPayload | null, fallbackIllustration: string) => string;
  cacheRoleSession: (roleId: string, session: SessionPayload) => void;
  clearAllSendingSessions: () => void;
  clearSessionSending: (sessionKey: string) => void;
  commitActiveSession: (nextSession: SessionPayload | null) => void;
  updateCommittedActiveSession: (updater: (current: SessionPayload | null) => SessionPayload | null) => void;
  appendSessionErrorMessage: (sessionKey: string, message: string) => void;
  loadRolesFromBridge: () => Promise<RoleRecord[] | null>;
  openRole: (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<boolean>;
  buildNavigationEntry: (view: { kind: "chat" }, roleId?: string) => NavigationEntry;
  pushNavigationEntry: (entry: NavigationEntry) => void;
};

/** Owns bridge events, persisted desktop shell state, and first-load refresh flow. */
export function useDesktopBridgeLifecycle({
  activeRoleId,
  activeIllustration,
  setActiveRoleId,
  setActiveIllustration,
  setHealth,
  setError,
  setNotice,
  setEvents,
  setWindowMaximized,
  setUnreadCounts,
  activeRoleIdRef,
  activeSessionRef,
  mainViewRef,
  rolesRef,
  chooseIllustration,
  cacheRoleSession,
  clearAllSendingSessions,
  clearSessionSending,
  commitActiveSession,
  updateCommittedActiveSession,
  appendSessionErrorMessage,
  loadRolesFromBridge,
  openRole,
  buildNavigationEntry,
  pushNavigationEntry,
}: UseDesktopBridgeLifecycleArgs) {
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
  }, [activeRoleId]);

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
        if (event.method !== "chat.delta") {
          setEvents((items) => [...items, { method: event.method, payload: event.payload }].slice(-12));
        }
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
            setActiveIllustration((current) => chooseIllustration(currentRole, session, current));
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
  }, [
    activeRoleIdRef,
    activeSessionRef,
    appendSessionErrorMessage,
    cacheRoleSession,
    chooseIllustration,
    clearAllSendingSessions,
    clearSessionSending,
    commitActiveSession,
    mainViewRef,
    rolesRef,
    setActiveIllustration,
    setError,
    setEvents,
    setHealth,
    setNotice,
    setUnreadCounts,
    setWindowMaximized,
    updateCommittedActiveSession,
  ]);

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
      pushNavigationEntry(buildNavigationEntry({ kind: "chat" }, preferredRoleId ?? ""));
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [
    activeRoleIdRef,
    buildNavigationEntry,
    loadRolesFromBridge,
    openRole,
    pushNavigationEntry,
    setError,
    setHealth,
    setWindowMaximized,
  ]);

  return {
    refreshBridge,
    restartBridge,
  };
}
