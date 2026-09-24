import { startTransition, useCallback, useEffect } from "react";
import { refreshPluginEnabledState } from "../plugins/pluginEnabledStateStore";
import {
  applyChatStreamDelta,
  applyChatToolCompleted,
  applyChatToolStarted,
  failChatStream,
  finishChatStream,
} from "../chat/chatStreamingState";
import { useLatestRef } from "../shared/useLatestRef";
import { parseChatTurnMetrics } from "../chat/chatTurnMetrics";
import { getRoleIdFromSession, isProactiveAssistantMessage, type NavigationEntry } from "./appState";
import { shouldProcessDesktopBridgeEventSynchronously } from "./desktopBridgeEventPriority";
import {
  mergeSessionSummaryAndMessage,
  parseSessionMessageUpdatePayload,
} from "./useDesktopSessionState";
import type { RoleRecord, SessionPayload, AppMainView } from "../shared/types";
import { errorMessage, type FeedbackReporter } from "../shared/feedback/feedbackStore";

type UseDesktopBridgeLifecycleArgs = {
  activeRoleId: string;
  activeIllustration: string;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  setHealth: React.Dispatch<React.SetStateAction<string>>;
  /** The latest bridge failure reason, shown by the offline banner; cleared once the bridge is healthy. */
  setBridgeError: React.Dispatch<React.SetStateAction<string>>;
  feedback: FeedbackReporter;
  healthRef: React.MutableRefObject<string>;
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
  completeChatTurn: (sessionKey: string, turnId: string) => void;
  isCurrentChatTurn: (sessionKey: string, turnId: string) => boolean;
  isChatTurnCancelling: (sessionKey: string, turnId: string) => boolean;
  commitActiveSession: (nextSession: SessionPayload | null) => void;
  updateCommittedActiveSession: (updater: (current: SessionPayload | null) => SessionPayload | null) => void;
  appendSessionErrorMessage: (sessionKey: string, message: string, detail?: string) => void;
  loadRolesFromBridge: () => Promise<RoleRecord[] | null>;
  openRole: (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<boolean>;
  buildNavigationEntry: (view: { kind: "chat" }, roleId?: string) => NavigationEntry;
  pushNavigationEntry: (entry: NavigationEntry) => void;
};

/** How long background session updates are batched before the role list (and its previews) is re-read. */
const rolePreviewRefreshDelayMs = 1000;

/** Owns bridge events, persisted desktop shell state, and first-load refresh flow. */
export function useDesktopBridgeLifecycle({
  activeRoleId,
  activeIllustration,
  setActiveRoleId,
  setActiveIllustration,
  setHealth,
  setBridgeError,
  feedback,
  healthRef,
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
  completeChatTurn,
  isCurrentChatTurn,
  isChatTurnCancelling,
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
    completeChatTurn,
    isCurrentChatTurn,
    isChatTurnCancelling,
    commitActiveSession,
    loadRolesFromBridge,
    openRole,
    pushNavigationEntry,
    updateCommittedActiveSession,
  });

  const reportPluginStateError = useCallback((error: unknown) => {
    feedback.error(`插件状态刷新失败：${errorMessage(error)}`);
  }, [feedback]);

  /**
   * Re-reads health, the plugin roster and roles, then reopens the active role.
   * Returns whether the bridge answered, so callers can tell a recovery apart
   * from a still-offline bridge.
   */
  const refreshBridge = useCallback(async (): Promise<boolean> => {
    setHealth("connecting");
    const res = await window.miraDesktop.invoke({
      method: "health",
      payload: {},
    });
    if (res.error) {
      setHealth("offline");
      setBridgeError(res.error.message);
      return false;
    }
    setHealth("online");
    setBridgeError("");
    void refreshPluginEnabledState().catch(reportPluginStateError);
    const nextRoles = await callbacksRef.current.loadRolesFromBridge();
    if (!nextRoles) {
      return true;
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
    return true;
  }, [activeRoleIdRef, callbacksRef, reportPluginStateError, setActiveIllustration, setActiveRoleId, setBridgeError, setHealth]);

  const restartBridge = useCallback(async (): Promise<void> => {
    setHealth("connecting");
    const result = await window.miraDesktop.restartBridge();
    if (!result.ok) {
      setHealth("offline");
      setBridgeError(result.lastError || "连接桥重启失败");
      feedback.error("重新连接失败，请稍后再试");
      return;
    }
    if (await refreshBridge()) feedback.success("连接已恢复");
  }, [feedback, refreshBridge, setBridgeError, setHealth]);

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
    // A background role's conversation moved (proactive message, another
    // channel): re-read the role list so its chat-list preview follows.
    // Debounced so a chatty group channel costs one roles.list per second.
    let rolePreviewRefreshTimer: number | null = null;
    const scheduleRolePreviewRefresh = () => {
      if (rolePreviewRefreshTimer !== null) return;
      rolePreviewRefreshTimer = window.setTimeout(() => {
        rolePreviewRefreshTimer = null;
        void callbacksRef.current.loadRolesFromBridge();
      }, rolePreviewRefreshDelayMs);
    };
    const offEvents = window.miraDesktop.onEvent((event) => {
      const callbacks = callbacksRef.current;
      const processEvent = () => {
        if (event.method === "window.state") {
          setWindowMaximized(Boolean(event.payload.isMaximized));
          setWindowVisible(Boolean(event.payload.isVisible));
          return;
        }

        if (event.method === "bridge.exit") {
          callbacks.clearAllSendingSessions();
          setHealth("offline");
          setBridgeError(String(event.payload.message ?? "bridge exited"));
          return;
        }

        // The main process restarts an exited bridge on the next request
        // (any invoke, e.g. the title bar's refresh) and announces it here.
        // Only an offline renderer needs to reload: a restart it drives itself
        // (`restartBridge`, `refreshBridge`, first load) is already
        // "connecting" and reloads on its own when the request returns.
        if (event.method === "bridge.ready") {
          if (healthRef.current !== "offline") return;
          void refreshBridge().then((recovered) => {
            if (recovered) feedback.success("连接已恢复");
          });
          return;
        }

        if (event.method === "runtime.applied") {
          void refreshPluginEnabledState().catch(reportPluginStateError);
          void callbacks.loadRolesFromBridge().catch((error: unknown) => {
            feedback.error(`角色列表加载失败：${errorMessage(error)}`);
          });
          return;
        }

        if (event.method === "session.updated") {
          const update = parseSessionMessageUpdatePayload(event.payload);
          if (!update) return;
          const currentSession = activeSessionRef.current;
          const currentView = mainViewRef.current;
          const isActiveSession = currentSession?.key === update.session.key;
          const session = mergeSessionSummaryAndMessage(
            isActiveSession ? currentSession : null,
            update.session,
            update.message,
            update.messages,
          );
          const roleId = getRoleIdFromSession(session);
          const isVisibleChat = isActiveSession && currentView.kind === "chat";
          if (!isActiveSession && roleId) scheduleRolePreviewRefresh();
          if (isActiveSession) {
            if (roleId) {
              callbacks.cacheRoleSession(roleId, session);
            }
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
        const eventTurnId = String(event.payload.turn_id ?? "");
        if (["chat.delta", "chat.tool.started", "chat.tool.completed", "chat.done", "chat.error"].includes(event.method)
          && !callbacks.isCurrentChatTurn(eventSessionKey, eventTurnId)) return;
        if (event.method === "chat.delta") {
          const currentSession = activeSessionRef.current;
          if (!currentSession || eventSessionKey !== currentSession.key) return;
          const delta = String(event.payload.content_delta ?? "");
          const thinkingDelta = String(event.payload.thinking_delta ?? "");
          if (!delta && !thinkingDelta) return;
          callbacks.updateCommittedActiveSession((current) => {
            if (!current) return current;
            return applyChatStreamDelta(current, delta, thinkingDelta, eventTurnId);
          });
          return;
        }

        if (event.method === "chat.tool.started") {
          const currentSession = activeSessionRef.current;
          if (!currentSession || eventSessionKey !== currentSession.key) return;
          const argumentsValue = event.payload.arguments;
          if (!argumentsValue || typeof argumentsValue !== "object" || Array.isArray(argumentsValue)) return;
          callbacks.updateCommittedActiveSession((current) => {
            if (!current || current.key !== eventSessionKey) return current;
            return applyChatToolStarted(current, {
              turnId: eventTurnId,
              iteration: Number(event.payload.iteration ?? 1),
              callId: String(event.payload.call_id ?? ""),
              toolName: String(event.payload.tool_name ?? ""),
              arguments: argumentsValue as Record<string, unknown>,
            });
          });
          return;
        }

        if (event.method === "chat.tool.completed") {
          const currentSession = activeSessionRef.current;
          if (!currentSession || eventSessionKey !== currentSession.key) return;
          const argumentsValue = event.payload.arguments;
          const finalArgumentsValue = event.payload.final_arguments;
          if (!argumentsValue || typeof argumentsValue !== "object" || Array.isArray(argumentsValue)) return;
          if (!finalArgumentsValue || typeof finalArgumentsValue !== "object" || Array.isArray(finalArgumentsValue)) return;
          callbacks.updateCommittedActiveSession((current) => {
            if (!current || current.key !== eventSessionKey) return current;
            return applyChatToolCompleted(current, {
              turnId: eventTurnId,
              iteration: Number(event.payload.iteration ?? 1),
              callId: String(event.payload.call_id ?? ""),
              toolName: String(event.payload.tool_name ?? ""),
              arguments: argumentsValue as Record<string, unknown>,
              finalArguments: finalArgumentsValue as Record<string, unknown>,
              status: String(event.payload.status ?? "error"),
              resultPreview: String(event.payload.result_preview ?? ""),
            });
          });
          return;
        }

        if (event.method === "chat.done") {
          callbacks.updateCommittedActiveSession((current) => {
            if (!current || current.key !== eventSessionKey) return current;
            return finishChatStream(current, parseChatTurnMetrics({
              total_tokens: event.payload.total_tokens,
              thinking_duration_ms: event.payload.thinking_duration_ms,
            }));
          });
          callbacks.completeChatTurn(eventSessionKey, eventTurnId);
          return;
        }

        if (event.method === "chat.error") {
          const cancelling = callbacks.isChatTurnCancelling(eventSessionKey, eventTurnId);
          const currentSession = activeSessionRef.current;
          if (!cancelling && currentSession && eventSessionKey === currentSession.key) {
            callbacks.updateCommittedActiveSession((current) => {
              if (!current || current.key !== eventSessionKey) return current;
              return failChatStream(current);
            });
            // Shown inline as an error bubble in the conversation, not as a toast.
            callbacks.appendSessionErrorMessage(
              currentSession.key,
              String(event.payload.message ?? "对话失败"),
              String(event.payload.detail ?? ""),
            );
          }
          callbacks.completeChatTurn(eventSessionKey, eventTurnId);
        }
      };

      if (shouldProcessDesktopBridgeEventSynchronously(event.method)) {
        processEvent();
        return;
      }
      startTransition(processEvent);
    });
    return () => {
      offEvents();
      if (rolePreviewRefreshTimer !== null) window.clearTimeout(rolePreviewRefreshTimer);
    };
  }, [
    activeRoleIdRef,
    activeSessionRef,
    callbacksRef,
    feedback,
    healthRef,
    mainViewRef,
    refreshBridge,
    reportPluginStateError,
    rolesRef,
    setActiveIllustration,
    setBridgeError,
    setHealth,
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
        setBridgeError(bridgeStatus.lastError);
        return;
      }
      const healthRes = await window.miraDesktop.invoke({
        method: "health",
        payload: {},
      });
      if (cancelled) return;
      if (healthRes.error) {
        setHealth("offline");
        setBridgeError(healthRes.error.message);
        return;
      }
      setHealth("online");
      setBridgeError("");

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
    setBridgeError,
    setHealth,
    setWindowMaximized,
    setWindowVisible,
  ]);

  return {
    refreshBridge,
    restartBridge,
  };
}
