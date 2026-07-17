import { startTransition, useCallback, useEffect } from "react";
import { ensureChatMessageRenderId } from "../chat/chatMessageIdentity";
import { useLatestRef } from "../shared/useLatestRef";
import { getRoleIdFromSession, isProactiveAssistantMessage, type NavigationEntry } from "./appState";
import { shouldProcessDesktopBridgeEventSynchronously } from "./desktopBridgeEventPriority";
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
  setWindowVisible: React.Dispatch<React.SetStateAction<boolean>>;
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
  setWindowVisible,
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
  const callbacksRef = useLatestRef({
    appendSessionErrorMessage,
    buildNavigationEntry,
    cacheRoleSession,
    chooseIllustration,
    clearAllSendingSessions,
    clearSessionSending,
    commitActiveSession,
    loadRolesFromBridge,
    openRole,
    pushNavigationEntry,
    updateCommittedActiveSession,
  });

  const refreshBridge = useCallback(async (): Promise<void> => {
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
    const nextRoles = await callbacksRef.current.loadRolesFromBridge();
    if (!nextRoles) {
      return;
    }
    const currentRoleId = activeRoleIdRef.current;
    if (currentRoleId) {
      const activeRole = nextRoles.find((item) => item.id === currentRoleId) ?? null;
      if (activeRole) {
        await callbacksRef.current.openRole(activeRole.id, activeRole, { recordHistory: false });
      } else if (nextRoles[0]) {
        await callbacksRef.current.openRole(nextRoles[0].id, nextRoles[0], { recordHistory: false });
      } else {
        setActiveRoleId("");
        callbacksRef.current.commitActiveSession(null);
        setActiveIllustration("");
      }
    } else if (nextRoles[0]) {
      await callbacksRef.current.openRole(nextRoles[0].id, nextRoles[0], { recordHistory: false });
    }
    setNotice("连接桥已刷新。");
  }, [activeRoleIdRef, callbacksRef, setActiveIllustration, setActiveRoleId, setError, setHealth, setNotice]);

  const restartBridge = useCallback(async (): Promise<void> => {
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
  }, [refreshBridge, setError, setHealth, setNotice]);

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
      const callbacks = callbacksRef.current;
      if (event.method !== "chat.delta") {
        startTransition(() => {
          setEvents((items) => [...items, { method: event.method, payload: event.payload }].slice(-12));
        });
      }

      const processEvent = () => {
        if (event.method === "window.state") {
          setWindowMaximized(Boolean(event.payload.isMaximized));
          setWindowVisible(Boolean(event.payload.isVisible));
          return;
        }

        if (event.method === "bridge.exit") {
          callbacks.clearAllSendingSessions();
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
            callbacks.cacheRoleSession(roleId, session);
          }
          if (isActiveSession) {
            callbacks.commitActiveSession(session);
            const currentRole = rolesRef.current.find((item) => item.id === activeRoleIdRef.current) ?? null;
            setActiveIllustration((current) => callbacks.chooseIllustration(currentRole, session, current));
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
          callbacks.updateCommittedActiveSession((current) => {
            if (!current) return current;
            const messages = [...current.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "assistant" && !last.id) {
              last.content += delta;
            } else {
              messages.push(ensureChatMessageRenderId({ role: "assistant", content: delta }));
            }
            return { ...current, messages };
          });
          return;
        }

        if (event.method === "chat.done") {
          callbacks.clearSessionSending(eventSessionKey);
          return;
        }

        if (event.method === "chat.error") {
          callbacks.clearSessionSending(eventSessionKey);
          const currentSession = activeSessionRef.current;
          if (!currentSession || eventSessionKey !== currentSession.key) return;
          const message = String(event.payload.message ?? "对话失败");
          setError(message);
          callbacks.appendSessionErrorMessage(currentSession.key, message);
        }
      };

      if (shouldProcessDesktopBridgeEventSynchronously(event.method)) {
        processEvent();
        return;
      }
      startTransition(processEvent);
    });
    return off;
  }, [
    activeRoleIdRef,
    activeSessionRef,
    callbacksRef,
    mainViewRef,
    rolesRef,
    setActiveIllustration,
    setError,
    setEvents,
    setHealth,
    setNotice,
    setUnreadCounts,
    setWindowMaximized,
    setWindowVisible,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      const currentWindowState = await window.miraDesktop.windowState();
      if (cancelled) return;
      setWindowMaximized(currentWindowState.isMaximized);
      setWindowVisible(currentWindowState.isVisible);

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

      const nextRoles = await callbacksRef.current.loadRolesFromBridge();
      if (cancelled || !nextRoles) {
        return;
      }
      const preferredRoleId =
        nextRoles.find((item) => item.id === activeRoleIdRef.current)?.id
        ?? nextRoles.find((item) => item.id === window.localStorage.getItem("miraDesktop.activeRoleId"))?.id
        ?? nextRoles[0]?.id;
      if (preferredRoleId) {
        const preferredRole = nextRoles.find((item) => item.id === preferredRoleId) ?? null;
        void callbacksRef.current.openRole(preferredRoleId, preferredRole, { recordHistory: false });
      }
      callbacksRef.current.pushNavigationEntry(
        callbacksRef.current.buildNavigationEntry({ kind: "chat" }, preferredRoleId ?? ""),
      );
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [
    activeRoleIdRef,
    callbacksRef,
    setError,
    setHealth,
    setWindowMaximized,
    setWindowVisible,
  ]);

  return {
    refreshBridge,
    restartBridge,
  };
}
