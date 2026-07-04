import type React from "react";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { DesktopAppFrame } from "./app/DesktopAppFrame";
import {
  chatLatestImageSidebarDefaultWidth,
  chatLatestImageSidebarMaxWidth,
  chatLatestImageSidebarMinWidth,
  createEmptyNewRoleForm,
  createEmptyRoleForm,
  historySidebarDefaultWidth,
  historySidebarMaxWidth,
  historySidebarMinWidth,
  sidebarAnimationDurationMs,
  sidebarAutoCollapseWindowWidth,
  sidebarCollapseThreshold,
  sidebarDefaultWidth,
  sidebarMaxWidth,
  sidebarMinWidth,
  type PendingMessageNavigation,
  type WorkspaceFeedback,
} from "./app/appState";
import { useDesktopSessionState } from "./app/useDesktopSessionState";
import { useDesktopUiEffects } from "./app/useDesktopUiEffects";
import { useChatImageState } from "./app/useChatImageState";
import { useChatInteractions } from "./app/useChatInteractions";
import { useNavigationHistory } from "./app/useNavigationHistory";
import { useRoleManagement } from "./app/useRoleManagement";
import { useRoleSearch } from "./app/roleSearch";
import { buildDesktopViewModel } from "./app/desktopSelectors";
import type { RoleSessionCache } from "./chat/roleSessionCache";
import { useImageStudioState } from "./image/useImageStudioState";
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
  const openRoleRef = useRef<(
    (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<void>
  ) | null>(null);
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
    openRoleRef,
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
  });

  const {
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
  } = useDesktopSessionState({
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
  });

  openRoleRef.current = openRole;

  const { searchingSessions, searchResults, getMessageKey } = useRoleSearch({
    roles,
    showSearchDialog,
    searchQuery,
    activeRoleId,
    activeSession,
    fetchRoleSession,
    cacheRoleSession,
  });

  async function rememberIllustration(roleId: string, illustration: string): Promise<void> {
    await window.miraDesktop.invoke({
      method: "session.updateDisplayState",
      payload: {
        role_id: roleId,
        active_illustration: illustration,
      },
    });
  }

  const pendingDeleteRole = roles.find((role) => role.id === pendingDeleteRoleId) ?? null;

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
    activeSessionKey,
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

  const {
    openChatImagePreview,
    openSelectedChatImageLightbox,
    closeSelectedChatImageLightbox,
    locateSelectedChatImageMessage,
    addSelectedChatImageToAssetLibrary,
    selectPreviousChatImage,
    selectNextChatImage,
  } = useChatImageState({
    activeRoleId,
    activeRole,
    activeSessionKey,
    selectedChatImagePath,
    setSelectedChatImagePath,
    chatImageLightboxOpen,
    setChatImageLightboxOpen,
    setAddingChatImageToAssetLibrary,
    resolvedChatImagePath,
    selectedChatImageIndex,
    selectedChatImageEntry,
    chatImageHistory,
    latestChatGeneratedImagePath,
    sidebarAutoCollapseWindowWidth,
    openChatLatestImageSidebar: chatLatestImageSidebar.open,
    loadRolesFromBridge,
    queueMessageNavigation,
    setError,
    setNotice,
    setSidebarAnimating,
    setSidebarCollapsed,
  });

  const {
    createRole,
    saveRole,
    saveRoleAssets,
    confirmDeleteRole,
    pickRoleAssets,
    removeRoleAsset,
  } = useRoleManagement({
    activeRoleId,
    detailRoleId,
    detailRole,
    activeIllustration,
    selectedAvatarAsset,
    selectedChatBackground,
    roleFormRef,
    newRoleFormRef,
    activeRoleIdRef,
    setCreating,
    setSavingRole,
    setSavingRoleAssets,
    setDeletingRole,
    setPendingRoleCardAction,
    setWorkspaceFeedback,
    setError,
    setNotice,
    setRoles,
    setActiveRoleId,
    setSelectedAvatarAsset,
    setSelectedChatBackground,
    setActiveIllustration,
    updateRoleForm,
    updateNewRoleForm,
    openRoleWorkspace,
    buildNavigationEntry,
    replaceNavigationEntry,
    loadRolesFromBridge,
    openRole,
    applyRoleSnapshot,
    commitActiveSession,
    removeCachedRoleSession,
    rememberIllustration,
  });

  const {
    openRoleDetail,
    openRoleAssets,
    pickChatAttachments,
    beginAttachmentDrag,
    removePendingChatAttachment,
    copyChatMessage,
    quoteChatMessage,
    clearChatReplyTarget,
    jumpToChatMessage,
  } = useChatInteractions({
    activeRoleId,
    roles,
    activeSessionRef,
    applyRoleSnapshot,
    openRoleWorkspace,
    openRole,
    setNotice,
    setError,
    setPendingChatAttachments,
    setChatReplyTarget,
    setHighlightedMessageKey,
  });

  useDesktopUiEffects({
    sidebarAnimating,
    setSidebarAnimating,
    activeSessionKey,
    pendingMessageNavigation,
    activeRoleId,
    setHighlightedMessageKey,
    setPendingMessageNavigation,
    notice,
    setNotice,
    workspaceFeedback,
    setWorkspaceFeedback,
    highlightedMessageKey,
    previewIllustrations,
    activeIllustration,
    persistedChatBackground: detailRole?.chat_background_abs ?? "",
    setActiveIllustration,
    sidebarAnimationDurationMs,
  });

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
      onConfirmDeleteRole={() => void confirmDeleteRole(pendingDeleteRoleId, () => setPendingDeleteRoleId(""))}
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
