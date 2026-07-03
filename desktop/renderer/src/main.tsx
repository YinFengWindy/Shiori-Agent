import type React from "react";
import { startTransition, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { ChatSurface } from "./chat/ChatSurface";
import { ChatImageLightbox } from "./chat/ChatImageLightbox";
import {
  buildOptimisticUserChatMessage,
  normalizeChatAttachmentPaths,
} from "./chat/chatComposerState";
import {
  collectChatImageHistory,
  findChatImageHistoryEntry,
  findChatImageHistoryIndex,
  resolveChatImageSelection,
} from "./chat/chatImageHistory";
import { ConfirmDialog } from "./roles/ConfirmDialog";
import { RoleAssetsPage } from "./roles/RoleAssetsPage";
import { RoleCreatePage } from "./roles/RoleCreatePage";
import { RoleDetailPage } from "./roles/RoleDetailPage";
import { RoleManagementPage } from "./roles/RoleManagementPage";
import { ImageStudioPage } from "./image/ImageStudioPage";
import { ImageStudioSidebar } from "./image/ImageStudioSidebar";
import { useImageStudioState } from "./image/useImageStudioState";
import { reconcileRoles } from "./roles/roleListState";
import { RoleSearchDialog } from "./roles/RoleSearchDialog";
import { RoleSidebar } from "./roles/RoleSidebar";
import { RoleWorkspaceSidebar, type RoleWorkspaceSectionId } from "./roles/RoleWorkspaceSidebar";
import { SettingsPage } from "./settings/SettingsPage";
import { SettingsSidebar, type SettingsSectionId } from "./settings/SettingsSidebar";
import { toFileUrl } from "./shared/format";
import { cx } from "./shared/styles";
import { useRightSidebarState } from "./shared/useRightSidebarState";
import type {
  AppMainView,
  ChatReplyTarget,
  EventLog,
  NewRoleFormState,
  PendingRoleCardAction,
  RoleFormState,
  RoleRecord,
  RoleSearchResult,
  SessionPayload,
} from "./shared/types";
import { TitleBar } from "./shell/TitleBar";
import "./styles.css";

const sidebarMinWidth = 220;
const sidebarMaxWidth = 400;
const sidebarDefaultWidth = 220;
const sidebarCollapseThreshold = sidebarMinWidth / 2;
const historySidebarMinWidth = 126;
const historySidebarMaxWidth = 280;
const historySidebarDefaultWidth = 126;
const chatLatestImageSidebarMinWidth = 180;
const chatLatestImageSidebarMaxWidth = 360;
const chatLatestImageSidebarDefaultWidth = 220;
const sidebarAnimationDurationMs = 480;
const sidebarAutoCollapseWindowWidth = 980;
const minRoleCardBusyMs = 600;

type SearchableSessionRecord = {
  roleId: string;
  roleName: string;
  roleAvatarAbs: string | null;
  session: SessionPayload;
};

type NavigationEntry = {
  view: AppMainView;
  activeRoleId: string;
  settingsSection: SettingsSectionId;
};

type WorkspaceFeedback = {
  tone: "success" | "error";
  message: string;
};

type PendingMessageNavigation = {
  roleId: string;
  messageKey: string;
};

function cloneView(view: AppMainView): AppMainView {
  if (view.kind === "role-detail") {
    return { kind: "role-detail", roleId: view.roleId };
  }
  if (view.kind === "role-assets") {
    return { kind: "role-assets", roleId: view.roleId };
  }
  return { kind: view.kind };
}

function viewsEqual(left: AppMainView, right: AppMainView): boolean {
  if (left.kind !== right.kind) {
    return false;
  }
  if (left.kind === "role-detail" && right.kind === "role-detail") {
    return left.roleId === right.roleId;
  }
  if (left.kind === "role-assets" && right.kind === "role-assets") {
    return left.roleId === right.roleId;
  }
  return true;
}

function navigationEntriesEqual(left: NavigationEntry, right: NavigationEntry): boolean {
  return (
    viewsEqual(left.view, right.view)
    && left.activeRoleId === right.activeRoleId
    && left.settingsSection === right.settingsSection
  );
}

function createEmptyRoleForm(): RoleFormState {
  return {
    name: "",
    description: "",
    systemPrompt: "",
    nsfwMemoryEnabled: false,
    avatarSource: "",
    illustrationSources: [],
    removedIllustrations: [],
  };
}

function createEmptyNewRoleForm(): NewRoleFormState {
  return {
    name: "",
    description: "",
    systemPrompt: "",
  };
}

function createPendingRoleRecord(
  roleId: string,
  form: NewRoleFormState,
): RoleRecord {
  const timestamp = new Date().toISOString();
  return {
    id: roleId,
    name: form.name.trim() || "新角色",
    description: form.description,
    system_prompt: form.systemPrompt,
    runtime_config: {},
    avatar: null,
    avatar_abs: null,
    chat_background: null,
    chat_background_abs: null,
    illustrations: [],
    illustrations_abs: [],
    created_at: timestamp,
    updated_at: timestamp,
  };
}

function getRoleIdFromSession(session: SessionPayload): string {
  const metadataRoleId = String(session.metadata.role_id ?? "").trim();
  if (metadataRoleId) {
    return metadataRoleId;
  }
  return session.key.startsWith("role:") ? session.key.slice(5) : "";
}

function isProactiveAssistantMessage(session: SessionPayload): boolean {
  const lastMessage = session.messages[session.messages.length - 1];
  if (!lastMessage || lastMessage.role !== "assistant") {
    return false;
  }
  return Boolean(lastMessage.metadata?.proactive);
}

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
  const [sending, setSending] = useState(false);
  const [pendingRoleCardAction, setPendingRoleCardAction] = useState<PendingRoleCardAction>(null);
  const [showSearchDialog, setShowSearchDialog] = useState(false);
  const [pendingDeleteRoleId, setPendingDeleteRoleId] = useState("");
  const [workspaceFeedback, setWorkspaceFeedback] = useState<WorkspaceFeedback | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchingSessions, setSearchingSessions] = useState(false);
  const [searchIndex, setSearchIndex] = useState<SearchableSessionRecord[]>([]);
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
  const mainViewRef = useRef<AppMainView>({ kind: "chat" });
  const rolesRef = useRef<RoleRecord[]>([]);
  const navigationHistoryRef = useRef<NavigationEntry[]>([]);
  const navigationHistoryIndexRef = useRef(-1);
  const draftRef = useRef("");
  const pendingChatAttachmentsRef = useRef<string[]>([]);
  const roleFormRef = useRef<RoleFormState>(createEmptyRoleForm());
  const newRoleFormRef = useRef<NewRoleFormState>(createEmptyNewRoleForm());
  const lastNonSettingsViewRef = useRef<AppMainView>({ kind: "chat" });
  const [canGoBack, setCanGoBack] = useState(false);
  const [canGoForward, setCanGoForward] = useState(false);

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

  function buildNavigationEntry(
    view: AppMainView,
    roleId = activeRoleIdRef.current,
    section = settingsSection,
  ): NavigationEntry {
    const resolvedRoleId = view.kind === "role-detail" || view.kind === "role-assets" ? view.roleId : roleId;
    return {
      view: cloneView(view),
      activeRoleId: resolvedRoleId,
      settingsSection: section,
    };
  }

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

  function getMessageKey(roleId: string, messageId: string | null, messageIndex: number | null): string {
    if (messageId) return String(messageId);
    if (messageIndex == null) return "";
    const session = activeRoleId === roleId
      ? (activeSession ?? searchIndex.find((item) => item.roleId === roleId)?.session ?? null)
      : (searchIndex.find((item) => item.roleId === roleId)?.session ?? null);
    const message = session?.messages[messageIndex];
    if (!message) return "";
    return String(message.id ?? `${message.role}-${messageIndex}`);
  }

  function queueMessageNavigation(roleId: string, messageKey: string): void {
    const nextMessageKey = messageKey.trim();
    if (!roleId || !nextMessageKey) {
      return;
    }
    setPendingMessageNavigation({ roleId, messageKey: nextMessageKey });
  }

  function truncateSearchPreview(value: string, query: string): string {
    const compactValue = value.replace(/\s+/g, " ").trim();
    if (!compactValue) return "空消息";
    const compactQuery = query.trim().toLowerCase();
    if (!compactQuery) return compactValue.slice(0, 88);
    const hitIndex = compactValue.toLowerCase().indexOf(compactQuery);
    if (hitIndex < 0) return compactValue.slice(0, 88);
    const start = Math.max(0, hitIndex - 16);
    const end = Math.min(compactValue.length, hitIndex + compactQuery.length + 44);
    const prefix = start > 0 ? "..." : "";
    const suffix = end < compactValue.length ? "..." : "";
    return `${prefix}${compactValue.slice(start, end)}${suffix}`;
  }

  function toggleSidebar(): void {
    setSidebarAnimating(true);
    if (sidebarCollapsed) {
      setSidebarWidth((current) => Math.min(sidebarMaxWidth, Math.max(sidebarMinWidth, current)));
      setSidebarCollapsed(false);
      return;
    }
    setSidebarCollapsed(true);
  }

  function openSettingsView(section: SettingsSectionId = "models"): void {
    lastNonSettingsViewRef.current = mainView;
    setSettingsSearch("");
    setSettingsSection(section);
    setSidebarAnimating(true);
    setSidebarCollapsed(false);
    setSidebarWidth((current) => Math.min(sidebarMaxWidth, Math.max(sidebarMinWidth, current)));
    setMainView({ kind: "settings" });
  }

  function openRoleWorkspaceView(nextView: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>): void {
    setSidebarAnimating(true);
    setSidebarCollapsed(false);
    setMainView(nextView);
  }

  function syncNavigationState(): void {
    setCanGoBack(navigationHistoryIndexRef.current > 0);
    setCanGoForward(
      navigationHistoryIndexRef.current >= 0
      && navigationHistoryIndexRef.current < navigationHistoryRef.current.length - 1,
    );
  }

  function pushNavigationEntry(entry: NavigationEntry): void {
    const nextHistory = navigationHistoryRef.current.slice(0, navigationHistoryIndexRef.current + 1);
    const previous = nextHistory[nextHistory.length - 1];
    if (previous && navigationEntriesEqual(previous, entry)) {
      navigationHistoryRef.current = nextHistory;
      navigationHistoryIndexRef.current = nextHistory.length - 1;
      syncNavigationState();
      return;
    }
    nextHistory.push(entry);
    navigationHistoryRef.current = nextHistory;
    navigationHistoryIndexRef.current = nextHistory.length - 1;
    syncNavigationState();
  }

  function replaceNavigationEntry(entry: NavigationEntry): void {
    if (navigationHistoryIndexRef.current < 0) {
      navigationHistoryRef.current = [entry];
      navigationHistoryIndexRef.current = 0;
      syncNavigationState();
      return;
    }
    const nextHistory = [...navigationHistoryRef.current];
    nextHistory[navigationHistoryIndexRef.current] = entry;
    navigationHistoryRef.current = nextHistory;
    syncNavigationState();
  }

  function openChatView(options?: { recordHistory?: boolean }): void {
    const nextView: AppMainView = { kind: "chat" };
    setMainView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
  }

  function openImageStudio(options?: { recordHistory?: boolean }): void {
    if (!roles.length) {
      setError("请先创建至少一个角色，再进入生图。");
      setNotice("");
      return;
    }
    const nextView: AppMainView = { kind: "image-studio" };
    setSidebarAnimating(true);
    setSidebarCollapsed(false);
    imageHistorySidebar.open();
    setMainView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
  }

  function openSettingsWorkspace(
    section: SettingsSectionId = "models",
    options?: { recordHistory?: boolean },
  ): void {
    openSettingsView(section);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry({ kind: "settings" }, activeRoleIdRef.current, section));
    }
  }

  function openRoleWorkspace(
    nextView: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>,
    options?: { recordHistory?: boolean },
  ): void {
    openRoleWorkspaceView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
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

  async function buildSearchIndex(nextRoles: RoleRecord[]): Promise<void> {
    if (!nextRoles.length) {
      setSearchIndex([]);
      return;
    }
    setSearchingSessions(true);
    try {
      const sessionRecords = await Promise.all(
        nextRoles.map(async (role) => {
          const { session } = await fetchRoleSession(role.id);
          if (!session) return null;
          return {
            roleId: role.id,
            roleName: role.name,
            roleAvatarAbs: role.avatar_abs,
            session,
          } satisfies SearchableSessionRecord;
        }),
      );
      setSearchIndex(sessionRecords.filter((item): item is SearchableSessionRecord => item !== null));
    } finally {
      setSearchingSessions(false);
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
    setActiveSession((current) => {
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
    if (!showSearchDialog) return;
    void buildSearchIndex(roles);
  }, [roles, showSearchDialog]);

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
          setSending(false);
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
          if (isActiveSession) {
            setActiveSession(session);
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

        const currentSession = activeSessionRef.current;
        if (!currentSession) return;

        if (String(event.payload.session_key ?? "") !== currentSession.key) return;

        if (event.method === "chat.delta") {
          const delta = String(event.payload.content_delta ?? "");
          if (!delta) return;
          setActiveSession((current) => {
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
          setSending(false);
          return;
        }

        if (event.method === "chat.error") {
          setSending(false);
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
        setActiveSession(null);
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
    if (activeRoleIdRef.current !== roleId) {
      setChatReplyTarget(null);
    }
    const role = roleOverride ?? roles.find((item) => item.id === roleId) ?? null;
    if (role) {
      applyRoleSnapshot(role);
      setError("");
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
    setActiveRoleId(roleId);
    setActiveSession(session);
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
    setSending(true);
    setError("");
    setDraft("");
    draftRef.current = "";
    setChatReplyTarget(null);
    setPendingChatAttachments([]);
    pendingChatAttachmentsRef.current = [];
    setActiveSession((current) =>
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
        setSending(false);
        const { session: recoveredSession } = await fetchRoleSession(roleId);
        if (recoveredSession) {
          setActiveSession((current) =>
            current?.key === sessionKey ? recoveredSession : current,
          );
        } else if (previousSession) {
          setActiveSession((current) =>
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
      setActiveSession((current) =>
        current?.key === nextSession.key ? nextSession : current,
      );
      setSending(false);
    } catch (error) {
      setSending(false);
      const { session: recoveredSession } = await fetchRoleSession(roleId);
      if (recoveredSession) {
        setActiveSession((current) =>
          current?.key === sessionKey ? recoveredSession : current,
        );
      } else if (previousSession) {
        setActiveSession((current) =>
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
      setActiveSession(null);
      setActiveIllustration("");
    }
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

  async function navigateHistory(direction: "back" | "forward"): Promise<void> {
    const delta = direction === "back" ? -1 : 1;
    const nextIndex = navigationHistoryIndexRef.current + delta;
    const nextEntry = navigationHistoryRef.current[nextIndex];
    if (!nextEntry) return;
    navigationHistoryIndexRef.current = nextIndex;
    syncNavigationState();

    setSettingsSection(nextEntry.settingsSection);
    if (nextEntry.view.kind === "settings") {
      openSettingsView(nextEntry.settingsSection);
      return;
    }
    if (nextEntry.view.kind === "image-studio") {
      openImageStudio({ recordHistory: false });
      return;
    }
    if (nextEntry.view.kind === "roles-list" || nextEntry.view.kind === "role-create") {
      openRoleWorkspaceView(nextEntry.view);
      return;
    }
    if (nextEntry.view.kind === "role-assets") {
      const assetsView = nextEntry.view;
      const assetsRole = roles.find((role) => role.id === assetsView.roleId) ?? null;
      if (!assetsRole) {
        openRoleWorkspaceView({ kind: "roles-list" });
        return;
      }
      applyRoleSnapshot(assetsRole);
      openRoleWorkspaceView(assetsView);
      void openRole(assetsView.roleId, assetsRole, { recordHistory: false });
      return;
    }
    if (nextEntry.view.kind === "role-detail") {
      const detailView = nextEntry.view;
      const detailRole = roles.find((role) => role.id === detailView.roleId) ?? null;
      if (!detailRole) {
        openRoleWorkspaceView({ kind: "roles-list" });
        return;
      }
      applyRoleSnapshot(detailRole);
      openRoleWorkspaceView(detailView);
      void openRole(detailView.roleId, detailRole, { recordHistory: false });
      return;
    }
    if (nextEntry.activeRoleId) {
      const nextRole = roles.find((role) => role.id === nextEntry.activeRoleId) ?? null;
      if (nextRole) {
        await openRole(nextRole.id, nextRole, { recordHistory: false });
      }
    }
    setMainView({ kind: "chat" });
  }

  const searchResults = (() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return [] satisfies RoleSearchResult[];

    const results: RoleSearchResult[] = [];
    for (const record of searchIndex) {
      if (record.roleName.toLowerCase().includes(query)) {
        results.push({
          roleId: record.roleId,
          roleName: record.roleName,
          roleAvatarAbs: record.roleAvatarAbs,
          sessionKey: record.session.key,
          matchedMessageTimestamp: record.session.updated_at ?? null,
          matchedMessageId: null,
          matchedMessageIndex: null,
          matchedMessagePreview: `角色 ${record.roleName}`,
          matchedField: "role",
        });
      }

      record.session.messages.forEach((message, messageIndex) => {
        const content = message.content.trim();
        if (!content) return;
        if (!content.toLowerCase().includes(query)) return;
        results.push({
          roleId: record.roleId,
          roleName: record.roleName,
          roleAvatarAbs: record.roleAvatarAbs,
          sessionKey: record.session.key,
          matchedMessageTimestamp: message.timestamp ?? null,
          matchedMessageId: message.id ?? null,
          matchedMessageIndex: messageIndex,
          matchedMessagePreview: truncateSearchPreview(content, query),
          matchedField: "message",
        });
      });
    }

    return results.slice(0, 60);
  })();

  const activeRole = roles.find((role) => role.id === activeRoleId) ?? null;
  const detailRoleId = mainView.kind === "role-detail" ? mainView.roleId : activeRoleId;
  const detailRole = roles.find((role) => role.id === detailRoleId) ?? null;
  const bridgeReady = health === "online";
  const roleFormDirty = Boolean(
    detailRole
      && (
        roleForm.name !== detailRole.name
        || roleForm.description !== detailRole.description
        || roleForm.systemPrompt !== detailRole.system_prompt
        || roleForm.nsfwMemoryEnabled !== Boolean(detailRole.runtime_config?.nsfw_memory_enabled)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
      )
  );

  const previewAvatar = roleForm.avatarSource || detailRole?.avatar_abs || null;

  const previewIllustrations = roleForm.illustrationSources.length
    ? roleForm.illustrationSources
    : (detailRole?.illustrations_abs ?? []).filter(
      (path) => !roleForm.removedIllustrations.includes(path),
    );
  const roleChatBackground = detailRole?.chat_background_abs ?? "";
  const visibleIllustration = activeIllustration || roleChatBackground;
  const visibleIllustrationUrl = visibleIllustration ? toFileUrl(visibleIllustration) : "";
  const chatBackgroundUrl = visibleIllustrationUrl;
  const headerTitle = sending && activeRole ? "正在输入中..." : (activeRole ? activeRole.name : "选择一个角色");
  const chatImageHistory = collectChatImageHistory(activeSession);
  const resolvedChatImagePath = resolveChatImageSelection(chatImageHistory, selectedChatImagePath);
  const selectedChatImageIndex = findChatImageHistoryIndex(chatImageHistory, resolvedChatImagePath);
  const selectedChatImageEntry = findChatImageHistoryEntry(chatImageHistory, resolvedChatImagePath);
  const latestChatGeneratedImagePath = chatImageHistory[chatImageHistory.length - 1]?.path ?? "";
  const selectedChatImagePosition = selectedChatImageIndex >= 0 ? selectedChatImageIndex + 1 : 0;

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
    <div className="app-frame grid h-screen grid-rows-app overflow-hidden bg-[var(--app-bg)]">
      <TitleBar
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
      />
      <div
        className={cx(
          "desktop-shell grid min-h-0 overflow-hidden bg-transparent",
          (resizingSidebar || imageHistorySidebar.resizing || chatLatestImageSidebar.resizing) && "sidebar-resizing cursor-col-resize select-none",
        )}
        style={{
          gridTemplateColumns: "minmax(0, auto) minmax(0, 1fr)",
        }}
      >
        <div
          className={cx(
            "sidebar-track relative min-h-0 overflow-hidden",
            sidebarAnimating && "transition-[width] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          )}
          style={{ width: sidebarCollapsed ? 0 : sidebarWidth }}
        >
          {mainView.kind === "settings" ? (
            <SettingsSidebar
              activeSection={settingsSection}
              animating={sidebarAnimating && !resizingSidebar}
              collapsed={sidebarCollapsed}
              dirty={settingsDirty}
              width={sidebarWidth}
              onBackToChat={() => openChatView()}
              onOpenSection={(section) => openSettingsWorkspace(section)}
              onSearchChange={setSettingsSearch}
              onBeginResize={beginSidebarResize}
              search={settingsSearch}
            />
          ) : imageStudioViewActive ? (
            <ImageStudioSidebar
              bridgeReady={bridgeReady}
              animating={sidebarAnimating && !resizingSidebar}
              collapsed={sidebarCollapsed}
              width={sidebarWidth}
              form={imageStudioState.form}
              nsfwEnabled={imageStudioState.nsfwEnabled}
              addQualityTags={imageStudioState.addQualityTags}
              undesiredContentPreset={imageStudioState.undesiredContentPreset}
              roleItems={imageStudioState.roleItems}
              submitting={imageStudioState.submitting}
              validationError={imageStudioState.validationError}
              onBackToChat={() => openChatView()}
              onBeginResize={beginSidebarResize}
              onChange={imageStudioState.onChange}
              onPickBaseImage={imageStudioState.onPickBaseImage}
              onSubmit={imageStudioState.onSubmit}
              onToggleAddQualityTags={imageStudioState.onToggleAddQualityTags}
              onChangeUndesiredContentPreset={imageStudioState.onChangeUndesiredContentPreset}
              onToggleNsfwEnabled={imageStudioState.onToggleNsfwEnabled}
            />
          ) : roleWorkspaceViewActive ? (
            <RoleWorkspaceSidebar
              activeSection={roleWorkspaceSection}
              animating={sidebarAnimating && !resizingSidebar}
              collapsed={sidebarCollapsed}
              width={sidebarWidth}
              onBackToChat={() => openChatView()}
              onOpenSection={(section) => {
                if (section === "role-create") {
                  openRoleWorkspace({ kind: "role-create" });
                  return;
                }
                openRoleWorkspace({ kind: "roles-list" });
              }}
              onBeginResize={beginSidebarResize}
            />
          ) : (
            <RoleSidebar
              roles={roles}
              activeRoleId={activeRoleId}
              unreadCounts={unreadCounts}
              animating={sidebarAnimating && !resizingSidebar}
              bridgeReady={bridgeReady}
              collapsed={sidebarCollapsed}
              width={sidebarWidth}
              onOpenSearch={() => setShowSearchDialog(true)}
              onOpenRolesWorkspace={() => openRoleWorkspace({ kind: "roles-list" })}
              onOpenRole={(roleId) => void openRole(roleId, null, { recordHistory: true })}
              onOpenImageStudio={() => openImageStudio()}
              onOpenSettings={() => openSettingsWorkspace()}
              onBeginResize={beginSidebarResize}
            />
          )}
        </div>
        <main className="chat-pane relative grid min-h-0 grid-cols-[minmax(0,1fr)] overflow-hidden rounded-l-[16px] border-b border-l border-t border-[#E4E4E4] bg-[var(--chat-bg)]">
          {roleWorkspaceViewActive && workspaceFeedback ? (
            <div
              className={cx(
                "absolute left-1/2 top-4 z-[6] -translate-x-1/2 rounded-[14px] border px-4 py-2.5 text-sm shadow-[0_8px_24px_rgba(15,23,42,0.08)]",
                workspaceFeedback.tone === "success"
                  ? "border-[rgba(26,106,58,0.18)] bg-[#edf8f0] text-[#1a6a3a]"
                  : "border-[rgba(176,58,58,0.18)] bg-[#fff1f1] text-[#9a2f2f]",
              )}
              aria-live="polite"
            >
              {workspaceFeedback.message}
            </div>
          ) : null}
          {mainView.kind === "chat" ? (
            <ChatSurface
              activeRole={activeRole}
              activeRoleId={activeRoleId}
              activeSession={activeSession}
              bridgeReady={bridgeReady}
              chatLatestImagePath={resolvedChatImagePath}
              chatLatestImagePosition={selectedChatImagePosition}
              chatLatestImageSidebarAnimating={chatLatestImageSidebar.animating && !chatLatestImageSidebar.resizing}
              chatLatestImageSidebarCollapsed={chatLatestImageSidebar.collapsed}
              chatLatestImageSidebarCount={chatImageHistory.length}
              chatLatestImageSidebarWidth={chatLatestImageSidebar.width}
              conversationEndRef={conversationEndRef}
              draft={draft}
              headerTitle={headerTitle}
              highlightedMessageKey={highlightedMessageKey}
              notice={notice}
              pendingChatAttachments={pendingChatAttachments}
              chatReplyTarget={chatReplyTarget}
              sending={sending}
              visibleIllustrationUrl={visibleIllustrationUrl}
              onBeginChatLatestImageSidebarResize={chatLatestImageSidebar.beginResize}
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
              onToggleChatLatestImageSidebar={chatLatestImageSidebar.toggle}
              onUpdateDraft={setDraft}
            />
          ) : null}
          {mainView.kind === "image-studio" ? (
            <ImageStudioPage
              activeRecord={imageStudioState.activeRecord}
              error={imageStudioState.error}
              generating={imageStudioState.submitting}
              history={imageStudioState.history}
              latestResult={imageStudioState.latestResult}
              requestSummary={imageStudioState.requestSummary}
              selectedRecordId={imageStudioState.selectedRecordId}
              historySidebarCollapsed={imageHistorySidebar.collapsed}
              historySidebarWidth={imageHistorySidebar.width}
              historySidebarAnimating={imageHistorySidebar.animating && !imageHistorySidebar.resizing}
              onSelectRecord={imageStudioState.onSelectRecord}
              onToggleHistorySidebar={imageHistorySidebar.toggle}
              onBeginHistorySidebarResize={imageHistorySidebar.beginResize}
            />
          ) : null}
          {mainView.kind === "roles-list" ? (
            <RoleManagementPage
              activeRoleId={activeRoleId}
              bridgeReady={bridgeReady}
              pendingCardAction={pendingRoleCardAction}
              roles={roles}
              onOpenRoleDetail={(roleId) => void openRoleDetail(roleId)}
              onDeleteRole={(roleId) => setPendingDeleteRoleId(roleId)}
            />
          ) : null}
          {mainView.kind === "role-create" ? (
            <RoleCreatePage
              bridgeReady={bridgeReady}
              creating={creating}
              form={newRoleForm}
              onBackToList={() => openRoleWorkspace({ kind: "roles-list" })}
              onCreateRole={() => void createRole()}
              onResetForm={resetNewRoleForm}
              onUpdateForm={updateNewRoleForm}
            />
          ) : null}
          {mainView.kind === "role-detail" ? (
            <RoleDetailPage
              activeRole={detailRole}
              activeRoleId={detailRoleId}
              activeIllustration={activeIllustration}
              bridgeReady={bridgeReady}
              previewAvatar={previewAvatar}
              chatBackgroundUrl={chatBackgroundUrl}
              roleForm={roleForm}
              roleFormDirty={roleFormDirty}
              savingRole={savingRole}
              onBackToList={() => openRoleWorkspace({ kind: "roles-list" })}
              onOpenAssetsPage={() => void openRoleAssets(detailRoleId)}
              onUpdateRoleForm={updateRoleForm}
              onResetRoleForm={resetRoleForm}
              onSaveRole={() => void saveRole()}
            />
          ) : null}
          {mainView.kind === "role-assets" ? (
            <RoleAssetsPage
              activeRole={detailRole}
              bridgeReady={bridgeReady}
              savingSelection={savingRoleAssets}
              selectedAvatarAsset={selectedAvatarAsset}
              selectedChatBackground={selectedChatBackground}
              onBackToDetail={() => openRoleWorkspace({ kind: "role-detail", roleId: detailRoleId })}
              onPickAssets={() => void pickRoleAssets()}
              onRemoveAsset={(path) => void removeRoleAsset(path)}
              onSelectAvatarAsset={setSelectedAvatarAsset}
              onSelectChatBackground={setSelectedChatBackground}
              onSaveSelections={(nextSelection) => void saveRoleAssets(nextSelection)}
            />
          ) : null}
          {mainView.kind === "settings" ? (
            <SettingsPage
              bridgeReady={bridgeReady}
              search={settingsSearch}
              section={settingsSection}
              onMetaChange={({ configPath, dirty }) => {
                setSettingsConfigPath(configPath);
                setSettingsDirty(dirty);
              }}
            />
          ) : null}
        </main>
      </div>
      <RoleSearchDialog
        open={showSearchDialog}
        query={searchQuery}
        searching={searchingSessions}
        results={searchResults}
        onClose={() => {
          setShowSearchDialog(false);
          setSearchQuery("");
        }}
        onSelectResult={(result) => {
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
        onUpdateQuery={setSearchQuery}
      />
      <ConfirmDialog
        open={Boolean(pendingDeleteRole)}
        title="确认删除角色"
        description={pendingDeleteRole ? `“${pendingDeleteRole.name}” 删除后会移除角色会话与相关素材。` : ""}
        confirmLabel="确认删除"
        busy={deletingRole}
        onClose={() => {
          if (deletingRole) return;
          setPendingDeleteRoleId("");
        }}
        onConfirm={() => void confirmDeleteRole()}
      />
      <ChatImageLightbox
        canAddToAssetLibrary={Boolean(activeRoleId && resolvedChatImagePath)}
        canGoToNext={selectedChatImageIndex >= 0 && selectedChatImageIndex < chatImageHistory.length - 1}
        canGoToPrevious={selectedChatImageIndex > 0}
        canLocateMessage={Boolean(activeRoleId && selectedChatImageEntry?.messageId)}
        imagePath={resolvedChatImagePath}
        addingToAssetLibrary={addingChatImageToAssetLibrary}
        open={chatImageLightboxOpen}
        onAddToAssetLibrary={() => void addSelectedChatImageToAssetLibrary()}
        onClose={closeSelectedChatImageLightbox}
        onGoToNext={selectNextChatImage}
        onGoToPrevious={selectPreviousChatImage}
        onLocateMessage={locateSelectedChatImageMessage}
      />
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
