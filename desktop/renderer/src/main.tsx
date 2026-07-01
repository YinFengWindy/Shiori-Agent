import type React from "react";
import { startTransition, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { ChatSurface } from "./chat/ChatSurface";
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
    avatar: null,
    avatar_abs: null,
    featured_image: null,
    featured_image_abs: null,
    illustrations: [],
    illustrations_abs: [],
    created_at: timestamp,
    updated_at: timestamp,
  };
}

function App(): React.ReactElement {
  const [health, setHealth] = useState("connecting");
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [activeRoleId, setActiveRoleId] = useState("");
  const [activeSession, setActiveSession] = useState<SessionPayload | null>(null);
  const [draft, setDraft] = useState("");
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
  const [pendingSearchTarget, setPendingSearchTarget] = useState<RoleSearchResult | null>(null);
  const [highlightedMessageKey, setHighlightedMessageKey] = useState("");
  const [mainView, setMainView] = useState<AppMainView>({ kind: "chat" });
  const [sidebarWidth, setSidebarWidth] = useState(sidebarDefaultWidth);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [resizingSidebar, setResizingSidebar] = useState(false);
  const [sidebarAnimating, setSidebarAnimating] = useState(false);
  const [activeIllustration, setActiveIllustration] = useState("");
  const [selectedAvatarAsset, setSelectedAvatarAsset] = useState("");
  const [selectedFeaturedImage, setSelectedFeaturedImage] = useState("");
  const [clearAvatar, setClearAvatar] = useState(false);
  const [clearIllustrations, setClearIllustrations] = useState(false);
  const [roleForm, setRoleForm] = useState(createEmptyRoleForm);
  const [newRoleForm, setNewRoleForm] = useState(createEmptyNewRoleForm);
  const [settingsSearch, setSettingsSearch] = useState("");
  const [settingsSection, setSettingsSection] = useState<SettingsSectionId>("models");
  const [settingsConfigPath, setSettingsConfigPath] = useState("");
  const [settingsDirty, setSettingsDirty] = useState(false);
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
  const [chatImagePreviewPath, setChatImagePreviewPath] = useState("");
  const [chatImagePreviewLoading, setChatImagePreviewLoading] = useState(false);
  const [windowMaximized, setWindowMaximized] = useState(false);
  const conversationEndRef = useRef<HTMLDivElement | null>(null);
  const openRoleRequestIdRef = useRef(0);
  const activeRoleIdRef = useRef("");
  const activeSessionRef = useRef<SessionPayload | null>(null);
  const navigationHistoryRef = useRef<NavigationEntry[]>([]);
  const navigationHistoryIndexRef = useRef(-1);
  const draftRef = useRef("");
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
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    if (mainView.kind !== "settings") {
      lastNonSettingsViewRef.current = mainView;
    }
  }, [mainView]);

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
    return role.illustrations_abs[0] ?? "";
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
    return mergedRoles;
  }

  function applyRoleSnapshot(role: RoleRecord, sessionOverride: SessionPayload | null = null): void {
    setActiveRoleId(role.id);
    activeRoleIdRef.current = role.id;
    updateRoleForm({
      name: role.name,
      description: role.description,
      systemPrompt: role.system_prompt,
      avatarSource: "",
      illustrationSources: [],
      removedIllustrations: [],
    });
    setSelectedAvatarAsset(role.avatar ?? "");
    setSelectedFeaturedImage(role.featured_image ?? role.illustrations[0] ?? "");
    setClearAvatar(false);
    setClearIllustrations(false);
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

  useEffect(() => {
    if (!activeRoleId) {
      setChatImagePreviewPath("");
      setChatImagePreviewLoading(false);
      return undefined;
    }

    let cancelled = false;
    setChatImagePreviewLoading(true);

    void (async () => {
      const response = await window.miraDesktop.invoke({
        method: "novelai.history",
        payload: {
          role_id: activeRoleId,
          limit: 1,
        },
      });
      if (cancelled) return;
      if (response.error) {
        setChatImagePreviewPath("");
        setChatImagePreviewLoading(false);
        return;
      }
      const records = Array.isArray(response.payload.records)
        ? response.payload.records as Array<{ output_paths?: string[] }>
        : [];
      setChatImagePreviewPath(records[0]?.output_paths?.[0] ?? "");
      setChatImagePreviewLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [activeRoleId]);

  function openChatImagePreview(path: string): void {
    const cleanPath = path.trim();
    if (!cleanPath) return;
    setChatImagePreviewPath(cleanPath);
    setChatImagePreviewLoading(false);
    chatLatestImageSidebar.open();
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
    if (highlightedMessageKey) return;
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeSession?.messages.length, highlightedMessageKey, sending]);

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
    if (!activeSession || !pendingSearchTarget) return;
    if (pendingSearchTarget.roleId !== activeRoleId) return;
    const messageKey = getMessageKey(
      pendingSearchTarget.roleId,
      pendingSearchTarget.matchedMessageId,
      pendingSearchTarget.matchedMessageIndex,
    );
    if (!messageKey) {
      setPendingSearchTarget(null);
      return;
    }
    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 12;

    const tryHighlight = () => {
      if (cancelled) return;
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-message-key]"))
        .find((item) => item.dataset.messageKey === messageKey);
      if (target) {
        setHighlightedMessageKey(messageKey);
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        setPendingSearchTarget(null);
        return;
      }
      attempts += 1;
      if (attempts >= maxAttempts) {
        setPendingSearchTarget(null);
        return;
      }
      window.setTimeout(tryHighlight, 80);
    };

    const frame = window.requestAnimationFrame(tryHighlight);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
    };
  }, [activeRoleId, activeSession, pendingSearchTarget, searchIndex]);

  useEffect(() => {
    const off = window.miraDesktop.onEvent((event) => {
      startTransition(() => {
        setEvents((items) => [...items, { method: event.method, payload: event.payload }].slice(-12));
        if (event.method === "window.state") {
          setWindowMaximized(Boolean(event.payload.isMaximized));
          return;
        }
        if (!activeSession) return;
        if (String(event.payload.session_key ?? "") !== activeSession.key) return;

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

        if (event.method === "session.updated") {
          const session = event.payload.session as SessionPayload | undefined;
          if (!session || session.key !== activeSession.key) return;
          setActiveSession(session);
          const role = roles.find((item) => item.id === activeRoleId) ?? null;
          setActiveIllustration((current) =>
            chooseIllustration(role, session, current),
          );
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
          appendSessionErrorMessage(activeSession.key, message);
          return;
        }

        if (event.method === "bridge.exit") {
          setSending(false);
          setHealth("offline");
          setError(String(event.payload.message ?? "bridge exited"));
          setNotice("连接桥已停止。你可以刷新或重启它。");
        }
      });
    });
    return off;
  }, [activeSession]);

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
      setSelectedFeaturedImage("");
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

  async function sendMessage(contentOverride?: string): Promise<void> {
    const content = (contentOverride ?? draftRef.current).trim();
    const roleId = activeRoleIdRef.current;
    const previousSession = activeSessionRef.current;
    const sessionKey = previousSession?.key ?? "";
    if (!content || !roleId || !sessionKey) return;
    setSending(true);
    setError("");
    setDraft("");
    draftRef.current = "";
    setActiveSession((current) =>
      current?.key === sessionKey
        ? {
            ...current,
            messages: [...current.messages, { role: "user", content }],
          }
        : current,
    );
    try {
      const res = await window.miraDesktop.invoke({
        method: "chat.send",
        payload: { role_id: roleId, content },
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
        setError(res.error.message);
        appendSessionErrorMessage(sessionKey, res.error.message);
        return;
      }
      const nextSession = res.payload.session as SessionPayload;
      setActiveSession((current) =>
        current?.key === nextSession.key ? nextSession : current,
      );
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
        avatar_source: nextRoleForm.avatarSource || undefined,
        illustration_sources: nextRoleForm.illustrationSources,
        removed_illustrations: nextRoleForm.removedIllustrations,
        clear_avatar: clearAvatar,
        clear_illustrations: clearIllustrations,
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
    setClearAvatar(false);
    setClearIllustrations(false);
    await openRole(updated.id, nextRoles?.find((item) => item.id === updated.id) ?? updated, { recordHistory: false });
    openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, updated.id));
    setWorkspaceFeedback({ tone: "success", message: "角色保存成功。" });
  }

  async function saveRoleAssets(nextSelection?: {
    avatarAsset?: string;
    featuredImage?: string;
  }): Promise<void> {
    if (!detailRoleId) return;
    setSavingRoleAssets(true);
    setError("");
    const pendingRoleForm = roleFormRef.current;
    const avatarAsset = nextSelection?.avatarAsset ?? selectedAvatarAsset;
    const featuredImage = nextSelection?.featuredImage ?? selectedFeaturedImage;
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        avatar_asset: avatarAsset || undefined,
        featured_image: featuredImage || undefined,
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
    setSelectedFeaturedImage(updated.featured_image ?? updated.illustrations[0] ?? "");
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
    setClearAvatar(false);
    updateRoleForm((current) => ({ ...current, avatarSource: files[0] }));
  }

  async function pickIllustrations(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: true });
    if (!files.length) return;
    setClearIllustrations(false);
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
    setSelectedFeaturedImage(updated.featured_image ?? updated.illustrations[0] ?? "");
    openRoleWorkspace({ kind: "role-assets", roleId: updated.id }, { recordHistory: false });
  }

  function clearAvatarSelection(): void {
    setClearAvatar(true);
    updateRoleForm((current) => ({ ...current, avatarSource: "" }));
  }

  function removeIllustrationSelection(path: string): void {
    const cleanPath = path.trim();
    if (!cleanPath) return;
    const isPendingLocalFile = roleFormRef.current.illustrationSources.includes(cleanPath);
    if (isPendingLocalFile) {
      updateRoleForm((current) => ({
        ...current,
        illustrationSources: current.illustrationSources.filter((item) => item !== cleanPath),
      }));
    } else {
      setClearIllustrations(false);
      updateRoleForm((current) => ({
        ...current,
        removedIllustrations: current.removedIllustrations.includes(cleanPath)
          ? current.removedIllustrations
          : [...current.removedIllustrations, cleanPath],
      }));
    }
    setActiveIllustration((current) => (current === cleanPath ? "" : current));
  }

  function clearIllustrationsSelection(): void {
    setClearIllustrations(true);
    updateRoleForm((current) => ({ ...current, illustrationSources: [], removedIllustrations: [] }));
    setActiveIllustration("");
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
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
        || clearAvatar
        || clearIllustrations
      )
  );

  const previewAvatar = clearAvatar
    ? null
    : (roleForm.avatarSource || detailRole?.avatar_abs || null);

  const previewIllustrations = clearIllustrations
    ? []
    : (roleForm.illustrationSources.length
        ? roleForm.illustrationSources
        : (detailRole?.illustrations_abs ?? []).filter(
          (path) => !roleForm.removedIllustrations.includes(path),
        ));
  const visibleIllustration = activeIllustration || previewIllustrations[0] || "";
  const visibleIllustrationUrl = visibleIllustration ? toFileUrl(visibleIllustration) : "";
  const featuredImageUrl = detailRole?.featured_image_abs || visibleIllustrationUrl;
  const headerTitle = sending && activeRole ? "正在输入中..." : (activeRole ? activeRole.name : "选择一个角色");
  const latestChatGeneratedImagePath = (() => {
    const messages = activeSession?.messages ?? [];
    for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
      const media = messages[messageIndex]?.media;
      if (!Array.isArray(media)) continue;
      for (let mediaIndex = media.length - 1; mediaIndex >= 0; mediaIndex -= 1) {
        const path = String(media[mediaIndex] ?? "").trim();
        if (!path) continue;
        const lower = path.toLowerCase();
        if (
          lower.endsWith(".png")
          || lower.endsWith(".jpg")
          || lower.endsWith(".jpeg")
          || lower.endsWith(".webp")
          || lower.endsWith(".gif")
          || lower.endsWith(".bmp")
        ) {
          return path;
        }
      }
    }
    return "";
  })();

  useEffect(() => {
    if (!latestChatGeneratedImagePath) return;
    setChatImagePreviewPath((current) => (current === latestChatGeneratedImagePath ? current : latestChatGeneratedImagePath));
    setChatImagePreviewLoading(false);
    chatLatestImageSidebar.open();
  }, [latestChatGeneratedImagePath]);

  useEffect(() => {
    if (previewIllustrations.length === 0) {
      if (activeIllustration) {
        setActiveIllustration("");
      }
      return;
    }
    if (!previewIllustrations.includes(activeIllustration)) {
      setActiveIllustration(previewIllustrations[0] ?? "");
    }
  }, [previewIllustrations, activeIllustration]);

  function resetRoleForm(): void {
    if (!detailRole) return;
    updateRoleForm({
      name: detailRole.name,
      description: detailRole.description,
      systemPrompt: detailRole.system_prompt,
      avatarSource: "",
      illustrationSources: [],
      removedIllustrations: [],
    });
    setClearAvatar(false);
    setClearIllustrations(false);
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
              roleItems={imageStudioState.roleItems}
              submitting={imageStudioState.submitting}
              validationError={imageStudioState.validationError}
              onBackToChat={() => openChatView()}
              onBeginResize={beginSidebarResize}
              onChange={imageStudioState.onChange}
              onPickBaseImage={imageStudioState.onPickBaseImage}
              onSubmit={imageStudioState.onSubmit}
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
              animating={sidebarAnimating && !resizingSidebar}
              bridgeReady={bridgeReady}
              collapsed={sidebarCollapsed}
              width={sidebarWidth}
              onOpenSearch={() => setShowSearchDialog(true)}
              onToggleRoleEditor={() => openRoleWorkspace({ kind: "roles-list" })}
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
              chatLatestImageLoading={chatImagePreviewLoading}
              chatLatestImagePath={chatImagePreviewPath}
              chatLatestImageSidebarAnimating={chatLatestImageSidebar.animating && !chatLatestImageSidebar.resizing}
              chatLatestImageSidebarCollapsed={chatLatestImageSidebar.collapsed}
              chatLatestImageSidebarWidth={chatLatestImageSidebar.width}
              conversationEndRef={conversationEndRef}
              draft={draft}
              headerTitle={headerTitle}
              highlightedMessageKey={highlightedMessageKey}
              notice={notice}
              sending={sending}
              visibleIllustrationUrl={visibleIllustrationUrl}
              onBeginChatLatestImageSidebarResize={chatLatestImageSidebar.beginResize}
              onOpenChatImagePreview={openChatImagePreview}
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
              featuredImageUrl={featuredImageUrl}
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
              selectedFeaturedImage={selectedFeaturedImage}
              onBackToDetail={() => openRoleWorkspace({ kind: "role-detail", roleId: detailRoleId })}
              onPickAssets={() => void pickRoleAssets()}
              onSelectAvatarAsset={setSelectedAvatarAsset}
              onSelectFeaturedImage={setSelectedFeaturedImage}
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
            setPendingSearchTarget(result);
          } else {
            setPendingSearchTarget(null);
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
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
