import type React from "react";
import { startTransition, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { DesktopAppFrame } from "./app/DesktopAppFrame";
import {
  chatLatestImageSidebarDefaultWidth,
  chatLatestImageSidebarMaxWidth,
  chatLatestImageSidebarMinWidth,
  createEmptyNewRoleForm,
  createEmptyRoleForm,
  createPendingRoleRecord,
  getRoleIdFromSession,
  historySidebarDefaultWidth,
  historySidebarMaxWidth,
  historySidebarMinWidth,
  isProactiveAssistantMessage,
  minRoleCardBusyMs,
  sidebarAnimationDurationMs,
  sidebarAutoCollapseWindowWidth,
  sidebarCollapseThreshold,
  sidebarDefaultWidth,
  sidebarMaxWidth,
  sidebarMinWidth,
  type PendingMessageNavigation,
  type WorkspaceFeedback,
} from "./app/appState";
import { useNavigationHistory } from "./app/useNavigationHistory";
import { useRoleSearch } from "./app/roleSearch";
import {
  buildOptimisticUserChatMessage,
  normalizeChatAttachmentPaths,
} from "./chat/chatComposerState";
import {
  readRoleSessionCache,
  removeRoleSessionCache,
  resolveImmediateRoleSession,
  retainRoleSessionCache,
  writeRoleSessionCache,
  type RoleSessionCache,
} from "./chat/roleSessionCache";
import { buildDesktopViewModel } from "./app/desktopSelectors";
import { useImageStudioState } from "./image/useImageStudioState";
import { reconcileRoles } from "./roles/roleListState";
import { type RoleWorkspaceSectionId } from "./roles/RoleWorkspaceSidebar";
import { type SettingsSectionId } from "./settings/SettingsSidebar";
import { useRightSidebarState } from "./shared/useRightSidebarState";
import type {
  AppMainView,
  ChatReplyTarget,
  EventLog,
  NewRoleFormState,
  PendingRoleCardAction,
  RoleFormState,
  RoleRecord,
  SessionPayload,
} from "./shared/types";
import "./styles.css";

function App(): React.ReactElement {
  const [health, setHealth] = useState("connecting");
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [activeRoleId, setActiveRoleId] = useState("");
  const [activeSession, setActiveSession] = useState<SessionPayload | null>(null);
  const [draft, setDraft] = useState("");
  const [chatReplyTarget, setChatReplyTarget] = useState<ChatReplyTarget | null>(null);
  const [pendingChatAttachments, setPendingChatAttachments] = useState<string[]>([]);
  const [events, setEvents] = useState<EventLog[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [creating, setCreating] = useState(false);
  const [savingRole, setSavingRole] = useState(false);
  const [savingRoleAssets, setSavingRoleAssets] = useState(false);
  const [deletingRole, setDeletingRole] = useState(false);
  // Track in-flight chat turns by session so role switches don't leak typing state into other chats.
  const [sendingSessions, setSendingSessions] = useState<Record<string, string>>({});
  const [pendingRoleCardAction, setPendingRoleCardAction] = useState<PendingRoleCardAction>(null);
  const [showSearchDialog, setShowSearchDialog] = useState(false);
  const [pendingDeleteRoleId, setPendingDeleteRoleId] = useState("");
  const [workspaceFeedback, setWorkspaceFeedback] = useState<WorkspaceFeedback | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [pendingMessageNavigation, setPendingMessageNavigation] = useState<PendingMessageNavigation | null>(null);
  const [highlightedMessageKey, setHighlightedMessageKey] = useState("");
  const [mainView, setMainView] = useState<AppMainView>({ kind: "chat" });
  const [sidebarWidth, setSidebarWidth] = useState(sidebarDefaultWidth);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [resizingSidebar, setResizingSidebar] = useState(false);
  const [sidebarAnimating, setSidebarAnimating] = useState(false);
  const [activeIllustration, setActiveIllustration] = useState("");
  const [selectedAvatarAsset, setSelectedAvatarAsset] = useState("");
  const [selectedChatBackground, setSelectedChatBackground] = useState("");
  const [roleForm, setRoleForm] = useState(createEmptyRoleForm);
  const [newRoleForm, setNewRoleForm] = useState(createEmptyNewRoleForm);
  const [settingsSearch, setSettingsSearch] = useState("");
  const [settingsSection, setSettingsSection] = useState<SettingsSectionId>("models");
  const [settingsConfigPath, setSettingsConfigPath] = useState("");
  const [settingsDirty, setSettingsDirty] = useState(false);
  const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({});
  const imageHistorySidebar = useRightSidebarState({
    minWidth: historySidebarMinWidth,
    maxWidth: historySidebarMaxWidth,
    defaultWidth: historySidebarDefaultWidth,
    animationDurationMs: sidebarAnimationDurationMs,
  });
  const chatLatestImageSidebar = useRightSidebarState({
    minWidth: chatLatestImageSidebarMinWidth,
    maxWidth: chatLatestImageSidebarMaxWidth,
    defaultWidth: chatLatestImageSidebarDefaultWidth,
    animationDurationMs: sidebarAnimationDurationMs,
    defaultCollapsed: true,
  });
  const [selectedChatImagePath, setSelectedChatImagePath] = useState("");
  const [chatImageLightboxOpen, setChatImageLightboxOpen] = useState(false);
  const [addingChatImageToAssetLibrary, setAddingChatImageToAssetLibrary] = useState(false);
  const [windowMaximized, setWindowMaximized] = useState(false);
  const conversationEndRef = useRef<HTMLDivElement | null>(null);
  const latestChatImageRef = useRef<{ sessionKey: string; latestPath: string }>({ sessionKey: "", latestPath: "" });
  const openRoleRequestIdRef = useRef(0);
  const activeRoleIdRef = useRef("");
  const activeSessionRef = useRef<SessionPayload | null>(null);
  const roleSessionCacheRef = useRef<RoleSessionCache>({});
  const mainViewRef = useRef<AppMainView>({ kind: "chat" });
  const rolesRef = useRef<RoleRecord[]>([]);
  const draftRef = useRef("");
  const pendingChatAttachmentsRef = useRef<string[]>([]);
  const sendingSessionsRef = useRef<Record<string, string>>({});
  const roleFormRef = useRef<RoleFormState>(createEmptyRoleForm());
  const newRoleFormRef = useRef<NewRoleFormState>(createEmptyNewRoleForm());
  const lastNonSettingsViewRef = useRef<AppMainView>({ kind: "chat" });

  useEffect(() => {
    roleFormRef.current = roleForm;
  }, [roleForm]);

  useEffect(() => {
    newRoleFormRef.current = newRoleForm;
  }, [newRoleForm]);

  useEffect(() => {
    activeSessionRef.current = activeSession;
  }, [activeSession]);

  useEffect(() => {
    rolesRef.current = roles;
  }, [roles]);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    pendingChatAttachmentsRef.current = pendingChatAttachments;
  }, [pendingChatAttachments]);

  useEffect(() => {
    sendingSessionsRef.current = sendingSessions;
  }, [sendingSessions]);

  useEffect(() => {
    if (mainView.kind !== "settings") {
      lastNonSettingsViewRef.current = mainView;
    }
    mainViewRef.current = mainView;
  }, [mainView]);

  useEffect(() => {
    if (mainView.kind !== "chat" || !activeRoleId) {
      return;
    }
    setUnreadCounts((current) => {
      if (!current[activeRoleId]) {
        return current;
      }
      const next = { ...current };
      delete next[activeRoleId];
      return next;
    });
  }, [mainView.kind, activeRoleId]);

  const roleWorkspaceViewActive =
    mainView.kind === "roles-list"
    || mainView.kind === "role-create"
    || mainView.kind === "role-detail"
    || mainView.kind === "role-assets";
  const imageStudioViewActive = mainView.kind === "image-studio";
  const roleWorkspaceSection: RoleWorkspaceSectionId =
    mainView.kind === "role-create"
      ? "role-create"
      : mainView.kind === "role-assets"
        ? "role-assets"
        : mainView.kind === "role-detail"
        ? "role-detail"
        : "roles-list";
  const imageStudioState = useImageStudioState({
    active: imageStudioViewActive,
    activeRole: roles.find((role) => role.id === activeRoleId) ?? null,
    roles,
  });

  function updateRoleForm(next: React.SetStateAction<RoleFormState>): void {
    const resolved = typeof next === "function"
      ? next(roleFormRef.current)
      : next;
    roleFormRef.current = resolved;
    setRoleForm(resolved);
  }

  function updateNewRoleForm(next: React.SetStateAction<NewRoleFormState>): void {
    const resolved = typeof next === "function"
      ? next(newRoleFormRef.current)
      : next;
    newRoleFormRef.current = resolved;
    setNewRoleForm(resolved);
  }

  function queueMessageNavigation(roleId: string, messageKey: string): void {
    const nextMessageKey = messageKey.trim();
    if (!roleId || !nextMessageKey) {
      return;
    }
    setPendingMessageNavigation({ roleId, messageKey: nextMessageKey });
  }

  const { searchingSessions, searchResults, getMessageKey } = useRoleSearch({
    roles,
    showSearchDialog,
    searchQuery,
    activeRoleId,
    activeSession,
    fetchRoleSession,
    cacheRoleSession,
  });

  const {
    canGoBack,
    canGoForward,
    buildNavigationEntry,
    replaceNavigationEntry,
    openChatView,
    openImageStudio,
    openSettingsWorkspace,
    openRoleWorkspace,
    navigateHistory,
    pushNavigationEntry,
  } = useNavigationHistory({
    mainView,
    settingsSection,
    activeRoleIdRef,
    lastNonSettingsViewRef,
    roles,
    setError,
    setNotice,
    setSettingsSearch,
    setSettingsSection,
    setSidebarAnimating,
    setSidebarCollapsed,
    setSidebarWidth,
    setMainView,
    imageHistorySidebarOpen: imageHistorySidebar.open,
    applyRoleSnapshot,
    openRole,
  });

  function toggleSidebar(): void {
    setSidebarAnimating(true);
    if (sidebarCollapsed) {
      setSidebarWidth((current) => Math.min(sidebarMaxWidth, Math.max(sidebarMinWidth, current)));
      setSidebarCollapsed(false);
      return;
    }
    setSidebarCollapsed(true);
  }

  function beginSidebarResize(event: React.PointerEvent<HTMLDivElement>): void {
    event.preventDefault();
    flushSync(() => {
      setSidebarAnimating(false);
      setResizingSidebar(true);
    });
    let dragCollapsed = sidebarCollapsed;

    function stopResize(): void {
      setResizingSidebar(false);
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
    }

    function resize(moveEvent: PointerEvent): void {
      if (moveEvent.clientX <= sidebarCollapseThreshold) {
        if (!dragCollapsed) {
          setSidebarAnimating(true);
          dragCollapsed = true;
        }
        setSidebarCollapsed(true);
        return;
      }
      if (dragCollapsed) {
        setSidebarAnimating(true);
        dragCollapsed = false;
      }
      setSidebarCollapsed(false);
      setSidebarWidth(Math.min(sidebarMaxWidth, Math.max(sidebarMinWidth, moveEvent.clientX)));
    }

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }

  function chooseIllustration(
    role: RoleRecord | null,
    session: SessionPayload | null,
    fallbackIllustration: string,
  ): string {
    if (!role) return "";
    const sessionIllustration = String(session?.metadata.active_illustration ?? "");
    if (role.illustrations_abs.includes(sessionIllustration)) {
      return sessionIllustration;
    }
    if (role.illustrations_abs.includes(fallbackIllustration)) {
      return fallbackIllustration;
    }
    const roleChatBackground = String(role.chat_background_abs ?? "");
    if (role.illustrations_abs.includes(roleChatBackground)) {
      return roleChatBackground;
    }
    return "";
  }

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

  function applyRoleSnapshot(role: RoleRecord, sessionOverride: SessionPayload | null = null): void {
    setActiveRoleId(role.id);
    activeRoleIdRef.current = role.id;
    updateRoleForm({
      name: role.name,
      description: role.description,
      systemPrompt: role.system_prompt,
      nsfwMemoryEnabled: Boolean(role.runtime_config?.nsfw_memory_enabled),
      avatarSource: "",
      illustrationSources: [],
      removedIllustrations: [],
    });
    setSelectedAvatarAsset(role.avatar ?? "");
    setSelectedChatBackground(role.chat_background ?? "");
    const savedIllustration = window.localStorage.getItem("miraDesktop.activeIllustration") ?? "";
    setActiveIllustration(chooseIllustration(role, sessionOverride, savedIllustration));
  }

  async function waitForMinimumRoleCardBusy(startedAt: number): Promise<void> {
    const elapsed = Date.now() - startedAt;
    if (elapsed >= minRoleCardBusyMs) {
      return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, minRoleCardBusyMs - elapsed));
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
  }, []);

  useEffect(() => {
    if (activeRoleId) {
      window.localStorage.setItem("miraDesktop.activeRoleId", activeRoleId);
    } else {
      window.localStorage.removeItem("miraDesktop.activeRoleId");
    }
    activeRoleIdRef.current = activeRoleId;
  }, [activeRoleId]);

  useEffect(() => {
    if (activeIllustration) {
      window.localStorage.setItem("miraDesktop.activeIllustration", activeIllustration);
    } else {
      window.localStorage.removeItem("miraDesktop.activeIllustration");
    }
  }, [activeIllustration]);

  useEffect(() => {
    if (!sidebarAnimating) return undefined;
    const timer = window.setTimeout(() => setSidebarAnimating(false), sidebarAnimationDurationMs + 40);
    return () => window.clearTimeout(timer);
  }, [sidebarAnimating]);

  function openChatImagePreview(path: string): void {
    const cleanPath = path.trim();
    if (!cleanPath) return;
    setSelectedChatImagePath(cleanPath);
    chatLatestImageSidebar.open();
  }

  function openSelectedChatImageLightbox(): void {
    if (!resolvedChatImagePath) return;
    setChatImageLightboxOpen(true);
  }

  function closeSelectedChatImageLightbox(): void {
    setChatImageLightboxOpen(false);
  }

  function locateSelectedChatImageMessage(): void {
    if (!activeRoleId || !selectedChatImageEntry?.messageId) {
      return;
    }
    setChatImageLightboxOpen(false);
    queueMessageNavigation(activeRoleId, selectedChatImageEntry.messageId);
  }

  async function addSelectedChatImageToAssetLibrary(): Promise<void> {
    if (!activeRoleId || !resolvedChatImagePath) return;
    if (activeRole?.illustrations_abs.includes(resolvedChatImagePath)) {
      setNotice("当前图片已在素材库中。");
      return;
    }

    setAddingChatImageToAssetLibrary(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: activeRoleId,
        illustration_sources: [resolvedChatImagePath],
      },
    });
    setAddingChatImageToAssetLibrary(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    await loadRolesFromBridge();
    setNotice("已加入素材库。");
  }

  function selectPreviousChatImage(): void {
    if (selectedChatImageIndex <= 0) return;
    const previousPath = chatImageHistory[selectedChatImageIndex - 1]?.path ?? "";
    if (!previousPath) return;
    setSelectedChatImagePath(previousPath);
  }

  function selectNextChatImage(): void {
    if (selectedChatImageIndex < 0 || selectedChatImageIndex >= chatImageHistory.length - 1) return;
    const nextPath = chatImageHistory[selectedChatImageIndex + 1]?.path ?? "";
    if (!nextPath) return;
    setSelectedChatImagePath(nextPath);
  }

  useEffect(() => {
    function collapseSidebarForNarrowWindow(): void {
      if (window.innerWidth < sidebarAutoCollapseWindowWidth) {
        setSidebarAnimating(true);
        setSidebarCollapsed(true);
      }
    }

    collapseSidebarForNarrowWindow();
    window.addEventListener("resize", collapseSidebarForNarrowWindow);
    return () => window.removeEventListener("resize", collapseSidebarForNarrowWindow);
  }, []);

  async function rememberIllustration(roleId: string, illustration: string): Promise<void> {
    await window.miraDesktop.invoke({
      method: "session.updateDisplayState",
      payload: {
        role_id: roleId,
        active_illustration: illustration,
      },
    });
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

  /** Appends a visible error bubble into the active chat flow. */
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

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!workspaceFeedback) return;
    const timer = window.setTimeout(() => setWorkspaceFeedback(null), 2200);
    return () => window.clearTimeout(timer);
  }, [workspaceFeedback]);

  useEffect(() => {
    if (!highlightedMessageKey) return;
    const timer = window.setTimeout(() => setHighlightedMessageKey(""), 2400);
    return () => window.clearTimeout(timer);
  }, [highlightedMessageKey]);

  useEffect(() => {
    if (!activeSession || !pendingMessageNavigation) return;
    if (pendingMessageNavigation.roleId !== activeRoleId) return;
    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 12;

    const tryHighlight = () => {
      if (cancelled) return;
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-message-key]"))
        .find((item) => item.dataset.messageKey === pendingMessageNavigation.messageKey);
      if (target) {
        setHighlightedMessageKey(pendingMessageNavigation.messageKey);
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        setPendingMessageNavigation(null);
        return;
      }
      attempts += 1;
      if (attempts >= maxAttempts) {
        setPendingMessageNavigation(null);
        return;
      }
      window.setTimeout(tryHighlight, 80);
    };

    const frame = window.requestAnimationFrame(tryHighlight);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
    };
  }, [activeRoleId, activeSession, pendingMessageNavigation]);

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
            const activeRoleId = activeRoleIdRef.current;
            const role = rolesRef.current.find((item) => item.id === activeRoleId) ?? null;
            setActiveIllustration((current) =>
              chooseIllustration(role, session, current),
            );
          }
          if (
            event.id === "proactive"
            && roleId
            && isProactiveAssistantMessage(session)
            && !isVisibleChat
          ) {
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
          if (!currentSession) return;
          if (eventSessionKey !== currentSession.key) return;
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
      if (cancelled) return;
      if (!nextRoles) {
        return;
      }
      const preferredRoleId =
        nextRoles.find((item) => item.id === activeRoleIdRef.current)?.id ??
        nextRoles.find((item) => item.id === window.localStorage.getItem("miraDesktop.activeRoleId"))?.id ??
        nextRoles[0]?.id;
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
  }, []);

  async function refreshSession(): Promise<void> {
    if (!activeRoleId) return;
    await openRole(activeRoleId, null, { recordHistory: false });
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
    const role = roleOverride ?? roles.find((item) => item.id === roleId) ?? null;
    if (role) {
      applyRoleSnapshot(role, cachedSession);
      setError("");
    }
    if (immediateSession !== activeSessionRef.current) {
      // Show the last cached chat for this role immediately while the bridge refreshes it in the background.
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
    const resolvedRole = roleOverride ?? latestRoles?.find((item) => item.id === roleId) ?? roles.find((item) => item.id === roleId) ?? null;
    if (resolvedRole) {
      applyRoleSnapshot(resolvedRole, session);
    } else {
      setActiveIllustration("");
      setSelectedAvatarAsset("");
      setSelectedChatBackground("");
    }
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry({ kind: "chat" }, roleId));
    } else if (mainView.kind === "chat") {
      replaceNavigationEntry(buildNavigationEntry({ kind: "chat" }, roleId));
    }
  }

  async function openRoleDetail(roleId: string): Promise<void> {
    const role = roles.find((item) => item.id === roleId) ?? null;
    if (role) {
      applyRoleSnapshot(role);
    }
    openRoleWorkspace({ kind: "role-detail", roleId });
    void openRole(roleId, role, { recordHistory: false });
  }

  async function openRoleAssets(roleId: string): Promise<void> {
    const role = roles.find((item) => item.id === roleId) ?? null;
    if (role) {
      applyRoleSnapshot(role);
    }
    openRoleWorkspace({ kind: "role-assets", roleId });
    if (activeRoleIdRef.current !== roleId || !activeSessionRef.current) {
      void openRole(roleId, role, { recordHistory: false });
    }
  }

  async function pickChatAttachments(): Promise<void> {
    const files = await window.miraDesktop.pickChatAttachments({ multiple: true });
    if (!files.length) {
      return;
    }
    setPendingChatAttachments((current) => normalizeChatAttachmentPaths([...current, ...files]));
  }

  function beginAttachmentDrag(path: string): void {
    const normalizedPath = path.trim();
    if (!normalizedPath) {
      return;
    }
    window.miraDesktop.startAttachmentDrag({ path: normalizedPath });
  }

  function removePendingChatAttachment(path: string): void {
    setPendingChatAttachments((current) => current.filter((item) => item !== path));
  }

  async function copyChatMessage(content: string): Promise<void> {
    const normalizedContent = content.trim();
    if (!normalizedContent) {
      setNotice("当前消息没有可复制的文本。");
      return;
    }
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(normalizedContent);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = normalizedContent;
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      setNotice("已复制消息。");
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  function quoteChatMessage(target: ChatReplyTarget): void {
    setChatReplyTarget((current) => (
      current
      && current.messageId === target.messageId
      && current.content === target.content
      && current.sender === target.sender
      ? current
      : target
    ));
  }

  function clearChatReplyTarget(): void {
    setChatReplyTarget((current) => (current ? null : current));
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

  function jumpToChatMessage(messageKey: string): void {
    const normalizedMessageKey = messageKey.trim();
    if (!normalizedMessageKey) {
      return;
    }
    if (highlightedMessageKey === normalizedMessageKey) {
      setHighlightedMessageKey("");
    }
    window.requestAnimationFrame(() => {
      setHighlightedMessageKey(normalizedMessageKey);
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-message-key]"))
        .find((item) => item.dataset.messageKey === normalizedMessageKey);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  async function sendMessage(contentOverride?: string): Promise<void> {
    const draftValue = contentOverride ?? draftRef.current;
    const content = draftValue.trim();
    const media = normalizeChatAttachmentPaths(pendingChatAttachmentsRef.current);
    const replyTarget = chatReplyTarget;
    const roleId = activeRoleIdRef.current;
    const previousSession = activeSessionRef.current;
    const sessionKey = previousSession?.key ?? "";
    if ((!content && media.length === 0) || !roleId || !sessionKey) return;
    // Keep the existing single-flight desktop send behavior even though typing state is tracked per session.
    if (Object.keys(sendingSessionsRef.current).length > 0) return;
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
            messages: [...current.messages, buildOptimisticUserChatMessage(content, media, replyTarget)],
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
          reply_to_message_id: replyTarget?.messageId ?? "",
          reply_to_content: replyTarget?.content ?? "",
          reply_to_sender: replyTarget?.sender ?? "",
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
        setChatReplyTarget(replyTarget);
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
      setChatReplyTarget(replyTarget);
      setPendingChatAttachments(media);
      pendingChatAttachmentsRef.current = media;
      const message = error instanceof Error ? error.message : String(error);
      setError(message);
      appendSessionErrorMessage(sessionKey, message);
    }
  }

  async function createRole(): Promise<void> {
    const name = newRoleFormRef.current.name.trim();
    const systemPrompt = newRoleFormRef.current.systemPrompt.trim();
    if (!name || !systemPrompt) {
      const message = "角色名称和系统提示词不能为空。";
      setError(message);
      setWorkspaceFeedback({ tone: "error", message: `角色创建失败：${message}` });
      return;
    }
    const pendingRoleId = `pending-create:${Date.now()}`;
    const pendingRole = createPendingRoleRecord(pendingRoleId, newRoleFormRef.current);
    const previousActiveRoleId = activeRoleIdRef.current;
    const startedAt = Date.now();
    setCreating(true);
    setError("");
    setWorkspaceFeedback(null);
    setPendingRoleCardAction({ roleId: pendingRoleId, action: "create" });
    setRoles((current) => [pendingRole, ...current]);
    applyRoleSnapshot(pendingRole);
    openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, pendingRoleId));
    const res = await window.miraDesktop.invoke({
      method: "roles.create",
      payload: {
        name,
        description: newRoleFormRef.current.description,
        system_prompt: systemPrompt,
      },
    });
    await waitForMinimumRoleCardBusy(startedAt);
    setCreating(false);
    if (res.error) {
      setPendingRoleCardAction(null);
      setRoles((current) => current.filter((item) => item.id !== pendingRoleId));
      setActiveRoleId(previousActiveRoleId);
      activeRoleIdRef.current = previousActiveRoleId;
      openRoleWorkspace({ kind: "role-create" }, { recordHistory: false });
      replaceNavigationEntry(buildNavigationEntry({ kind: "role-create" }, previousActiveRoleId));
      setError(res.error.message);
      setWorkspaceFeedback({ tone: "error", message: `角色创建失败：${res.error.message}` });
      return;
    }
    const role = res.payload.role as RoleRecord;
    activeRoleIdRef.current = role.id;
    setActiveRoleId(role.id);
    setPendingRoleCardAction({ roleId: role.id, action: "create" });
    setRoles((current) => {
      const withoutPending = current.filter((item) => item.id !== pendingRoleId);
      const existing = withoutPending.find((item) => item.id === role.id);
      if (existing) {
        return [role, ...withoutPending.filter((item) => item.id !== role.id)];
      }
      return [role, ...withoutPending];
    });
    applyRoleSnapshot(role);
    const nextRoles = await loadRolesFromBridge();
    const resolvedRole = nextRoles?.find((item) => item.id === role.id) ?? role;
    if (!nextRoles?.some((item) => item.id === role.id)) {
      setRoles((current) => {
        const existing = current.find((item) => item.id === role.id);
        if (existing) {
          return [resolvedRole, ...current.filter((item) => item.id !== role.id)];
        }
        return [resolvedRole, ...current];
      });
    }
    await openRole(role.id, resolvedRole, { recordHistory: false });
    openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, resolvedRole.id));
    setPendingRoleCardAction(null);
    updateNewRoleForm(createEmptyNewRoleForm());
    setWorkspaceFeedback({ tone: "success", message: "角色创建成功。" });
  }

  async function saveRole(): Promise<void> {
    if (!activeRoleId) return;
    setSavingRole(true);
    setError("");
    setWorkspaceFeedback(null);
    const nextRoleForm = roleFormRef.current;
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: activeRoleId,
        name: nextRoleForm.name,
        description: nextRoleForm.description,
        system_prompt: nextRoleForm.systemPrompt,
        runtime_config: {
          ...(detailRole?.runtime_config ?? {}),
          nsfw_memory_enabled: nextRoleForm.nsfwMemoryEnabled,
        },
        avatar_source: nextRoleForm.avatarSource || undefined,
        illustration_sources: nextRoleForm.illustrationSources,
        removed_illustrations: nextRoleForm.removedIllustrations,
      },
    });
    setSavingRole(false);
    if (res.error) {
      setError(res.error.message);
      setWorkspaceFeedback({ tone: "error", message: `角色保存失败：${res.error.message}` });
      return;
    }
    const updated = res.payload.role as RoleRecord;
    const nextRoles = await loadRolesFromBridge();
    updateRoleForm((current) => ({ ...current, avatarSource: "", illustrationSources: [], removedIllustrations: [] }));
    await openRole(updated.id, nextRoles?.find((item) => item.id === updated.id) ?? updated, { recordHistory: false });
    openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, updated.id));
    setWorkspaceFeedback({ tone: "success", message: "角色保存成功。" });
  }

  async function saveRoleAssets(nextSelection?: {
    avatarAsset?: string;
    chatBackground?: string;
  }): Promise<void> {
    if (!detailRoleId) return;
    setSavingRoleAssets(true);
    setError("");
    const pendingRoleForm = roleFormRef.current;
    const hasAvatarSelection = Boolean(
      nextSelection && Object.prototype.hasOwnProperty.call(nextSelection, "avatarAsset"),
    );
    const hasChatBackgroundSelection = Boolean(
      nextSelection && Object.prototype.hasOwnProperty.call(nextSelection, "chatBackground"),
    );
    const avatarAsset = hasAvatarSelection
      ? (nextSelection?.avatarAsset ?? "")
      : selectedAvatarAsset;
    const chatBackground = hasChatBackgroundSelection
      ? (nextSelection?.chatBackground ?? "")
      : selectedChatBackground;
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        avatar_asset: avatarAsset || undefined,
        chat_background: chatBackground || undefined,
        clear_avatar: hasAvatarSelection && !avatarAsset,
        clear_chat_background: hasChatBackgroundSelection && !chatBackground,
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    await loadRolesFromBridge();
    setSelectedAvatarAsset(updated.avatar ?? "");
    setSelectedChatBackground(updated.chat_background ?? "");
    if (hasChatBackgroundSelection) {
      const nextIllustration = updated.chat_background_abs ?? "";
      setActiveIllustration(nextIllustration);
      await rememberIllustration(updated.id, nextIllustration);
    }
    setNotice("角色素材已更新。");
    updateRoleForm({
      ...pendingRoleForm,
    });
    openRoleWorkspace({ kind: "role-assets", roleId: updated.id }, { recordHistory: false });
  }

  async function deleteRole(roleIdOverride?: string): Promise<void> {
    const roleId = roleIdOverride || activeRoleId;
    if (!roleId) return;
    const startedAt = Date.now();
    setDeletingRole(true);
    setPendingRoleCardAction({ roleId, action: "delete" });
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.delete",
      payload: { role_id: roleId },
    });
    await waitForMinimumRoleCardBusy(startedAt);
    setDeletingRole(false);
    if (res.error) {
      setPendingRoleCardAction(null);
      setError(res.error.message);
      return;
    }
    const nextRoles = (await loadRolesFromBridge()) ?? [];
    setPendingRoleCardAction(null);
    if (!roleIdOverride || roleId === activeRoleId) {
      setActiveRoleId("");
      commitActiveSession(null);
      setActiveIllustration("");
    }
    removeCachedRoleSession(roleId);
    setNotice("角色已删除。");
    if (nextRoles[0]) {
      await openRole(nextRoles[0].id, nextRoles[0], { recordHistory: false });
      openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
      replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, nextRoles[0].id));
      return;
    }
    openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, ""));
  }

  const pendingDeleteRole = roles.find((role) => role.id === pendingDeleteRoleId) ?? null;

  async function confirmDeleteRole(): Promise<void> {
    if (!pendingDeleteRoleId) return;
    const targetRoleId = pendingDeleteRoleId;
    setPendingDeleteRoleId("");
    await deleteRole(targetRoleId);
  }

  async function pickAvatar(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: false });
    if (!files[0]) return;
    updateRoleForm((current) => ({ ...current, avatarSource: files[0] }));
  }

  async function pickIllustrations(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: true });
    if (!files.length) return;
    updateRoleForm((current) => ({ ...current, illustrationSources: files, removedIllustrations: [] }));
  }

  async function pickRoleAssets(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: true });
    if (!files.length || !detailRoleId) return;
    setSavingRoleAssets(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        illustration_sources: files,
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    await loadRolesFromBridge();
    setSelectedAvatarAsset(updated.avatar ?? "");
    setSelectedChatBackground(updated.chat_background ?? "");
    openRoleWorkspace({ kind: "role-assets", roleId: updated.id }, { recordHistory: false });
  }

  async function removeRoleAsset(relPath: string): Promise<void> {
    const cleanPath = relPath.trim();
    if (!cleanPath || !detailRoleId || !detailRole) return;
    const removedIndex = detailRole.illustrations.findIndex((item) => item === cleanPath);
    const removedAbsPath = removedIndex >= 0 ? (detailRole.illustrations_abs[removedIndex] ?? "") : "";
    setSavingRoleAssets(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        removed_illustrations: [cleanPath],
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    await loadRolesFromBridge();
    setSelectedAvatarAsset(updated.avatar ?? "");
    setSelectedChatBackground(updated.chat_background ?? "");
    if (!removedAbsPath || activeIllustration === removedAbsPath) {
      const nextIllustration = updated.chat_background_abs ?? "";
      setActiveIllustration(nextIllustration);
      await rememberIllustration(updated.id, nextIllustration);
    }
    setNotice("角色素材已删除。");
    openRoleWorkspace({ kind: "role-assets", roleId: updated.id }, { recordHistory: false });
  }

  const {
    activeRole,
    detailRoleId,
    detailRole,
    bridgeReady,
    roleFormDirty,
    previewAvatar,
    previewIllustrations,
    visibleIllustrationUrl,
    chatBackgroundUrl,
    isVisibleChatSending,
    headerTitle,
    chatImageHistory,
    resolvedChatImagePath,
    selectedChatImageIndex,
    selectedChatImageEntry,
    latestChatGeneratedImagePath,
    selectedChatImagePosition,
  } = buildDesktopViewModel({
    roles,
    activeRoleId,
    mainView,
    roleForm,
    activeIllustration,
    activeSession,
    selectedChatImagePath,
    health,
    sendingSessions,
  });

  useEffect(() => {
    const sessionKey = activeSession?.key ?? "";
    if (!sessionKey) {
      latestChatImageRef.current = { sessionKey: "", latestPath: "" };
      return;
    }

    const previous = latestChatImageRef.current;
    if (previous.sessionKey !== sessionKey) {
      latestChatImageRef.current = { sessionKey, latestPath: latestChatGeneratedImagePath };
      return;
    }

    // Only auto-open when the active chat produces a newer image during this session.
    if (latestChatGeneratedImagePath && latestChatGeneratedImagePath !== previous.latestPath) {
      setSelectedChatImagePath(latestChatGeneratedImagePath);
      chatLatestImageSidebar.open();
    }
    latestChatImageRef.current = { sessionKey, latestPath: latestChatGeneratedImagePath };
  }, [activeSession?.key, latestChatGeneratedImagePath]);

  useEffect(() => {
    if (resolvedChatImagePath) return;
    if (chatImageLightboxOpen) {
      setChatImageLightboxOpen(false);
    }
  }, [chatImageLightboxOpen, resolvedChatImagePath]);

  useEffect(() => {
    if (previewIllustrations.length === 0) {
      if (activeIllustration) {
        setActiveIllustration("");
      }
      return;
    }
    if (!previewIllustrations.includes(activeIllustration)) {
      const persistedChatBackground = detailRole?.chat_background_abs ?? "";
      if (persistedChatBackground && previewIllustrations.includes(persistedChatBackground)) {
        setActiveIllustration(persistedChatBackground);
        return;
      }
      setActiveIllustration("");
    }
  }, [previewIllustrations, activeIllustration, detailRole?.chat_background_abs]);

  function resetRoleForm(): void {
    if (!detailRole) return;
    updateRoleForm({
      name: detailRole.name,
      description: detailRole.description,
      systemPrompt: detailRole.system_prompt,
      nsfwMemoryEnabled: Boolean(detailRole.runtime_config?.nsfw_memory_enabled),
      avatarSource: "",
      illustrationSources: [],
      removedIllustrations: [],
    });
    setNotice("角色表单已重置。");
  }

  function resetNewRoleForm(): void {
    updateNewRoleForm(createEmptyNewRoleForm());
    setWorkspaceFeedback({ tone: "success", message: "新建角色表单已重置。" });
  }

  return (
    <DesktopAppFrame
      sidebarCollapsed={sidebarCollapsed}
      windowMaximized={windowMaximized}
      canGoBack={canGoBack}
      canGoForward={canGoForward}
      canRefreshSession={Boolean(activeRoleId)}
      canEditRole={Boolean(activeRoleId)}
      onToggleSidebar={toggleSidebar}
      onGoBack={() => void navigateHistory("back")}
      onGoForward={() => void navigateHistory("forward")}
      onRefreshSession={() => void refreshSession()}
      onCreateRole={() => openRoleWorkspace({ kind: "role-create" })}
      onEditRole={() => openRoleWorkspace(activeRoleId ? { kind: "role-detail", roleId: activeRoleId } : { kind: "roles-list" })}
      onOpenSettings={() => openSettingsWorkspace()}
      onRefreshBridge={() => void refreshBridge()}
      onRestartBridge={() => void restartBridge()}
      shellResizing={resizingSidebar || imageHistorySidebar.resizing || chatLatestImageSidebar.resizing}
      sidebarState={{
        collapsed: sidebarCollapsed,
        width: sidebarWidth,
        animating: sidebarAnimating,
        resizing: resizingSidebar,
        onBeginResize: beginSidebarResize,
      }}
      mainView={mainView}
      settingsSection={settingsSection}
      settingsDirty={settingsDirty}
      settingsSearch={settingsSearch}
      onSettingsSearchChange={setSettingsSearch}
      onBackToChat={() => openChatView()}
      onOpenSettingsSection={(section) => openSettingsWorkspace(section)}
      imageStudioViewActive={imageStudioViewActive}
      roleWorkspaceViewActive={roleWorkspaceViewActive}
      roleWorkspaceSection={roleWorkspaceSection}
      onOpenRoleWorkspaceSection={(section) => {
        if (section === "role-create") {
          openRoleWorkspace({ kind: "role-create" });
          return;
        }
        openRoleWorkspace({ kind: "roles-list" });
      }}
      roles={roles}
      activeRoleId={activeRoleId}
      unreadCounts={unreadCounts}
      bridgeReady={bridgeReady}
      onOpenSearch={() => setShowSearchDialog(true)}
      onOpenRolesWorkspace={() => openRoleWorkspace({ kind: "roles-list" })}
      onOpenRole={(roleId) => void openRole(roleId, null, { recordHistory: true })}
      onOpenImageStudio={() => openImageStudio()}
      imageStudioState={imageStudioState}
      workspaceFeedback={workspaceFeedback}
      activeRole={activeRole}
      activeSession={activeSession}
      chatLatestImagePath={resolvedChatImagePath}
      chatLatestImagePosition={selectedChatImagePosition}
      chatLatestImageSidebar={chatLatestImageSidebar}
      chatLatestImageSidebarCount={chatImageHistory.length}
      conversationEndRef={conversationEndRef}
      draft={draft}
      headerTitle={headerTitle}
      highlightedMessageKey={highlightedMessageKey}
      notice={notice}
      pendingChatAttachments={pendingChatAttachments}
      chatReplyTarget={chatReplyTarget}
      isVisibleChatSending={isVisibleChatSending}
      visibleIllustrationUrl={visibleIllustrationUrl}
      onGoToNextChatImage={selectNextChatImage}
      onGoToPreviousChatImage={selectPreviousChatImage}
      onOpenChatImageLightbox={openSelectedChatImageLightbox}
      onOpenChatImagePreview={openChatImagePreview}
      onPickChatAttachments={() => void pickChatAttachments()}
      onOpenRoleDetail={() => void openRoleDetail(activeRoleId)}
      onJumpToMessage={jumpToChatMessage}
      onClearChatReplyTarget={clearChatReplyTarget}
      onBeginAttachmentDrag={beginAttachmentDrag}
      onCopyMessage={(content) => void copyChatMessage(content)}
      onQuoteMessage={quoteChatMessage}
      onRemovePendingChatAttachment={removePendingChatAttachment}
      onSendMessage={(contentOverride) => void sendMessage(contentOverride)}
      onUpdateDraft={setDraft}
      imageHistorySidebar={imageHistorySidebar}
      detailRole={detailRole}
      pendingRoleCardAction={pendingRoleCardAction}
      onOpenRoleManagementDetail={(roleId) => void openRoleDetail(roleId)}
      onRequestDeleteRole={setPendingDeleteRoleId}
      creating={creating}
      newRoleForm={newRoleForm}
      onBackToRoleList={() => openRoleWorkspace({ kind: "roles-list" })}
      onCreateNewRole={() => void createRole()}
      onResetNewRoleForm={resetNewRoleForm}
      onUpdateNewRoleForm={updateNewRoleForm}
      detailRoleId={detailRoleId}
      activeIllustration={activeIllustration}
      previewAvatar={previewAvatar}
      chatBackgroundUrl={chatBackgroundUrl}
      roleForm={roleForm}
      roleFormDirty={roleFormDirty}
      savingRole={savingRole}
      onOpenAssetsPage={() => void openRoleAssets(detailRoleId)}
      onUpdateRoleForm={updateRoleForm}
      onResetRoleForm={resetRoleForm}
      onSaveRole={() => void saveRole()}
      savingRoleAssets={savingRoleAssets}
      selectedAvatarAsset={selectedAvatarAsset}
      selectedChatBackground={selectedChatBackground}
      onBackToRoleDetail={() => openRoleWorkspace({ kind: "role-detail", roleId: detailRoleId })}
      onPickRoleAssets={() => void pickRoleAssets()}
      onRemoveRoleAsset={(path) => void removeRoleAsset(path)}
      onSelectAvatarAsset={setSelectedAvatarAsset}
      onSelectChatBackground={setSelectedChatBackground}
      onSaveRoleAssets={(nextSelection) => void saveRoleAssets(nextSelection)}
      onSettingsMetaChange={({ configPath, dirty }) => {
        setSettingsConfigPath(configPath);
        setSettingsDirty(dirty);
      }}
      showSearchDialog={showSearchDialog}
      searchQuery={searchQuery}
      searchingSessions={searchingSessions}
      searchResults={searchResults}
      onCloseSearchDialog={() => {
        setShowSearchDialog(false);
        setSearchQuery("");
      }}
      onSelectSearchResult={(result) => {
        setShowSearchDialog(false);
        setSearchQuery("");
        if (result.matchedField === "message") {
          const messageKey = getMessageKey(
            result.roleId,
            result.matchedMessageId,
            result.matchedMessageIndex,
          );
          if (messageKey) {
            queueMessageNavigation(result.roleId, messageKey);
          }
        } else {
          setPendingMessageNavigation(null);
          setHighlightedMessageKey("");
        }
        void openRole(result.roleId, null, { recordHistory: true });
      }}
      onUpdateSearchQuery={setSearchQuery}
      pendingDeleteRole={pendingDeleteRole}
      deletingRole={deletingRole}
      onCloseDeleteDialog={() => {
        if (deletingRole) return;
        setPendingDeleteRoleId("");
      }}
      onConfirmDeleteRole={() => void confirmDeleteRole()}
      canAddToAssetLibrary={Boolean(activeRoleId && resolvedChatImagePath)}
      canGoToNextLightboxImage={selectedChatImageIndex >= 0 && selectedChatImageIndex < chatImageHistory.length - 1}
      canGoToPreviousLightboxImage={selectedChatImageIndex > 0}
      canLocateLightboxMessage={Boolean(activeRoleId && selectedChatImageEntry?.messageId)}
      addingChatImageToAssetLibrary={addingChatImageToAssetLibrary}
      chatImageLightboxOpen={chatImageLightboxOpen}
      onAddSelectedChatImageToAssetLibrary={() => void addSelectedChatImageToAssetLibrary()}
      onCloseSelectedChatImageLightbox={closeSelectedChatImageLightbox}
      onLocateSelectedChatImageMessage={locateSelectedChatImageMessage}
    />
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
