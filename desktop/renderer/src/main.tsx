import type React from "react";
import { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
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
import { useDesktopViewSynchronization } from "./app/useDesktopViewSynchronization";
import { useDesktopBridgeLifecycle } from "./app/useDesktopBridgeLifecycle";
import { useDesktopUiEffects } from "./app/useDesktopUiEffects";
import { useChatImageState } from "./app/useChatImageState";
import { useChatInteractions } from "./app/useChatInteractions";
import { useNavigationHistory } from "./app/useNavigationHistory";
import { useRoleManagement } from "./app/useRoleManagement";
import { useRoleSearch } from "./app/roleSearch";
import { buildDesktopViewModel } from "./app/desktopSelectors";
import { useRolePresentation } from "./app/useRolePresentation";
import { useWorldWorkspacePresentation } from "./app/useWorldWorkspacePresentation";
import type { RoleSessionCache } from "./chat/roleSessionCache";
import { DesktopErrorBoundary } from "./diagnostics/DesktopErrorBoundary";
import { registerRendererGlobalDiagnostics } from "./diagnostics/rendererGlobalDiagnostics";
import { useImageStudioState } from "./image/useImageStudioState";
import { type PromptTagWorkspaceSectionId } from "./image/PromptTagWorkspaceSidebar";
import { createRoleFormFromRole } from "./roles/roleFormState";
import { type RoleWorkspaceSectionId } from "./roles/RoleWorkspaceSidebar";
import { useRoleFormAdapters } from "./roles/useRoleFormAdapters";
import { type SettingsSectionId } from "./settings/SettingsSidebar";
import { useLatestRef } from "./shared/useLatestRef";
import { useLeftSidebarState } from "./shared/useLeftSidebarState";
import { useRightSidebarState } from "./shared/useRightSidebarState";
import { createWorldBridgeClient } from "./world/bridgeClient";
import { useWorldWorkspaceController } from "./world/useWorldWorkspaceController";
import { WorldAppSurface } from "./world/WorldAppSurface";
import type {
  AppMainView,
  EventLog,
  PendingRoleCardAction,
  RoleRecord,
  SessionPayload,
} from "./shared/types";
import "./styles.css";

function App(): React.ReactElement {
  const [health, setHealth] = useState("connecting");
  const [promptTagWorkspaceSection, setPromptTagWorkspaceSection] = useState<PromptTagWorkspaceSectionId>("list");
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [activeRoleId, setActiveRoleId] = useState("");
  const [activeSession, setActiveSession] = useState<SessionPayload | null>(null);
  const [, setEvents] = useState<EventLog[]>([]);
  const [, setError] = useState("");
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
  const leftSidebar = useLeftSidebarState({
    minWidth: sidebarMinWidth,
    maxWidth: sidebarMaxWidth,
    defaultWidth: sidebarDefaultWidth,
    collapseThreshold: sidebarCollapseThreshold,
  });
  const [activeIllustration, setActiveIllustration] = useState("");
  const [selectedAvatarAsset, setSelectedAvatarAsset] = useState("");
  const [selectedChatBackground, setSelectedChatBackground] = useState("");
  const [roleForm, setRoleForm] = useState(createEmptyRoleForm);
  const [newRoleForm, setNewRoleForm] = useState(createEmptyNewRoleForm);
  const [settingsSearch, setSettingsSearch] = useState("");
  const [settingsSection, setSettingsSection] = useState<SettingsSectionId>("models");
  const [, setSettingsConfigPath] = useState("");
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
  const [selectedChatImageKey, setSelectedChatImageKey] = useState("");
  const [chatImageLightboxOpen, setChatImageLightboxOpen] = useState(false);
  const [addingChatImageToAssetLibrary, setAddingChatImageToAssetLibrary] = useState(false);
  const [windowMaximized, setWindowMaximized] = useState(false);
  const [windowVisible, setWindowVisible] = useState(true);
  const conversationEndRef = useRef<HTMLDivElement | null>(null);
  const openRoleRequestIdRef = useRef(0);
  const roleAssetSaveRequestIdRef = useRef(0);
  const activeRoleIdRef = useLatestRef(activeRoleId);
  const activeSessionRef = useLatestRef(activeSession);
  const roleSessionCacheRef = useRef<RoleSessionCache>({});
  const mainViewRef = useLatestRef<AppMainView>(mainView);
  const rolesRef = useLatestRef(roles);
  const sendingSessionsRef = useLatestRef(sendingSessions);
  const unreadCountsRef = useLatestRef(unreadCounts);
  const roleFormRef = useLatestRef(roleForm);
  const newRoleFormRef = useLatestRef(newRoleForm);
  const lastNonSettingsViewRef = useDesktopViewSynchronization({
    mainView,
    activeRoleId,
    setUnreadCounts,
  });

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
  const worldBridgeClient = useMemo(() => createWorldBridgeClient(), []);
  const worldController = useWorldWorkspaceController(worldBridgeClient);
  const worldWorkspace = useWorldWorkspacePresentation({
    roles,
    client: worldBridgeClient,
    controller: worldController,
  });

  const { updateRoleForm, updateNewRoleForm } = useRoleFormAdapters({
    roleFormRef,
    newRoleFormRef,
    setRoleForm,
    setNewRoleForm,
  });

  function queueMessageNavigation(roleId: string, messageKey: string): void {
    const nextMessageKey = messageKey.trim();
    if (!roleId || !nextMessageKey) {
      return;
    }
    setPendingMessageNavigation({ roleId, messageKey: nextMessageKey });
  }

  const { chooseIllustration, applyRoleSnapshot, rememberIllustration } = useRolePresentation({
    activeRoleIdRef,
    mainViewRef,
    roleFormRef,
    setActiveRoleId,
    setActiveIllustration,
    setSelectedAvatarAsset,
    setSelectedChatBackground,
    updateRoleForm,
  });

  const {
    canGoBack,
    canGoForward,
    buildNavigationEntry,
    replaceNavigationEntry,
    openChatView,
    openWorldWorkspace,
    openImageStudio,
    openPromptTagLibrary,
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
    setSidebarAnimating: leftSidebar.setAnimating,
    setSidebarCollapsed: leftSidebar.setCollapsed,
    setSidebarWidth: leftSidebar.setWidth,
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
    clearAllSendingSessions,
    clearSessionSending,
    appendSessionErrorMessage,
    openRole,
    sendMessage,
    commitActiveSession,
    updateCommittedActiveSession,
  } = useDesktopSessionState({
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
  });

  const { refreshBridge, restartBridge } = useDesktopBridgeLifecycle({
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
  });

  const { searchingSessions, searchResults, getMessageKey } = useRoleSearch({
    roles,
    showSearchDialog,
    searchQuery,
    activeRoleId,
    activeSession,
    fetchRoleSession,
    cacheRoleSession,
  });

  const pendingDeleteRole = roles.find((role) => role.id === pendingDeleteRoleId) ?? null;

  const {
    activeRole,
    detailRoleId,
    detailRole,
    bridgeReady,
    roleFormDirty,
    previewAvatar,
    previewIllustrations,
    currentMood,
    moodIllustrationUrl,
    roleSelfView,
    relationshipTags,
    lonelinessValue,
    visibleIllustrationUrl,
    chatBackgroundUrl,
    activeSessionKey,
    isVisibleChatSending,
    headerTitle,
    chatImageHistory,
    resolvedChatImagePath,
    selectedChatImageIndex,
    selectedChatImageEntry,
    latestChatGeneratedImageKey,
    selectedChatImagePosition,
  } = buildDesktopViewModel({
    roles,
    activeRoleId,
    mainView,
    roleForm,
    activeIllustration,
    activeSession,
    selectedChatImageKey,
    health,
    sendingSessions,
  });

  const {
    openChatImagePreview,
    openSelectedChatImageLightbox,
    closeSelectedChatImageLightbox,
    locateSelectedChatImageMessage,
    addSelectedChatImageToAssetLibrary,
    regenerateSelectedChatImage,
    regeneratingSelectedChatImage,
    selectPreviousChatImage,
    selectNextChatImage,
  } = useChatImageState({
    activeRoleId,
    activeRole,
    activeSessionKey,
    setSelectedChatImageKey,
    chatImageLightboxOpen,
    setChatImageLightboxOpen,
    setAddingChatImageToAssetLibrary,
    resolvedChatImagePath,
    selectedChatImageIndex,
    selectedChatImageEntry,
    chatImageHistory,
    latestChatGeneratedImageKey,
    openChatLatestImageSidebar: chatLatestImageSidebar.open,
    loadRolesFromBridge,
    updateCommittedActiveSession,
    queueMessageNavigation,
    setError,
    setNotice,
  });

  const {
    createRole,
    saveRole,
    saveRoleAssets,
    confirmDeleteRole,
    pickRoleAssets,
    removeRoleAsset,
    importRolePetPackage,
    removeRolePetPackage,
    selectRolePetPackage,
    updateRoleAssetOrganization,
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
    roleAssetSaveRequestIdRef,
  });

  const {
    openRoleDetail,
    openRoleAssets,
    beginAttachmentDrag,
    copyChatMessage,
    jumpToChatMessage,
  } = useChatInteractions({
    activeRoleId,
    roles,
    activeSessionRef,
    mainViewRef,
    applyRoleSnapshot,
    openRoleWorkspace,
    openRole,
    setNotice,
    setError,
    setHighlightedMessageKey,
  });

  useDesktopUiEffects({
    sidebarAnimating: leftSidebar.animating,
    setSidebarAnimating: leftSidebar.setAnimating,
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
    sidebarAutoCollapseWindowWidth,
    setSidebarCollapsed: leftSidebar.setCollapsed,
  });

  function resetRoleForm(): void {
    if (!detailRole) return;
    updateRoleForm(createRoleFormFromRole(detailRole));
    setNotice("角色表单已重置。");
  }

  function resetNewRoleForm(): void {
    updateNewRoleForm(createEmptyNewRoleForm());
    setWorkspaceFeedback({ tone: "success", message: "新建角色表单已重置。" });
  }

  if (mainView.kind === "world") {
    return <WorldAppSurface onExit={() => openChatView()}>{worldWorkspace.content}</WorldAppSurface>;
  }

  return (
    <DesktopAppFrame
      sidebarCollapsed={leftSidebar.collapsed}
      windowMaximized={windowMaximized}
      canGoBack={canGoBack}
      canGoForward={canGoForward}
      canRefreshSession={mainView.kind === "chat" && Boolean(activeRoleId)}
      canEditRole={mainView.kind === "chat" && Boolean(activeRoleId)}
      onToggleSidebar={leftSidebar.toggle}
      onGoBack={() => void navigateHistory("back", openRole)}
      onGoForward={() => void navigateHistory("forward", openRole)}
      onRefreshSession={() => void refreshSession()}
      onCreateRole={() => openRoleWorkspace({ kind: "role-create" })}
      onEditRole={() => openRoleWorkspace(activeRoleId ? { kind: "role-detail", roleId: activeRoleId } : { kind: "roles-list" })}
      onOpenSettings={() => openSettingsWorkspace()}
      onRefreshBridge={() => void refreshBridge()}
      onRestartBridge={() => void restartBridge()}
      shellResizing={leftSidebar.resizing || imageHistorySidebar.resizing || chatLatestImageSidebar.resizing}
      sidebarState={{
        collapsed: leftSidebar.collapsed,
        width: leftSidebar.width,
        animating: leftSidebar.animating,
        resizing: leftSidebar.resizing,
        onBeginResize: leftSidebar.beginResize,
      }}
      mainView={mainView}
      settingsSection={settingsSection}
      settingsDirty={settingsDirty}
      settingsSearch={settingsSearch}
      onSettingsSearchChange={setSettingsSearch}
      onBackToChat={() => openChatView()}
      onOpenSettingsSection={(section) => openSettingsWorkspace(section)}
      imageStudioViewActive={imageStudioViewActive}
      imagePromptTagsViewActive={mainView.kind === "image-prompt-tags"}
      promptTagWorkspaceSection={promptTagWorkspaceSection}
      onOpenPromptTagWorkspaceSection={setPromptTagWorkspaceSection}
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
      onOpenWorld={() => openWorldWorkspace()}
      onOpenRole={(roleId) => void openRole(roleId, null, { recordHistory: true })}
      onOpenImageStudio={() => openImageStudio()}
      onOpenPromptTagLibrary={() => { setPromptTagWorkspaceSection("list"); openPromptTagLibrary(); }}
      imageStudioState={imageStudioState}
      workspaceFeedback={workspaceFeedback}
      activeRole={activeRole}
      activeSession={activeSession}
      chatLatestImagePath={resolvedChatImagePath}
      chatLatestImagePosition={selectedChatImagePosition}
      chatLatestImageSidebar={chatLatestImageSidebar}
      chatLatestImageSidebarCount={chatImageHistory.length}
      currentMood={currentMood}
      moodIllustrationUrl={moodIllustrationUrl}
      roleSelfView={roleSelfView}
      relationshipTags={relationshipTags}
      lonelinessValue={lonelinessValue}
      conversationEndRef={conversationEndRef}
      headerTitle={headerTitle}
      highlightedMessageKey={highlightedMessageKey}
      notice={notice}
      isVisibleChatSending={isVisibleChatSending}
      visibleIllustrationUrl={visibleIllustrationUrl}
      windowVisible={windowVisible}
      onGoToNextChatImage={selectNextChatImage}
      onGoToPreviousChatImage={selectPreviousChatImage}
      onOpenChatImageLightbox={openSelectedChatImageLightbox}
      onOpenChatImagePreview={openChatImagePreview}
      onOpenRoleDetail={() => void openRoleDetail(activeRoleId)}
      onJumpToMessage={jumpToChatMessage}
      onBeginAttachmentDrag={beginAttachmentDrag}
      onCopyMessage={(content) => void copyChatMessage(content)}
      onSendMessage={sendMessage}
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
      onPickRoleAssets={(categoryId) => void pickRoleAssets(categoryId)}
      onUpdateRoleAssetOrganization={(categories, bindings, removedIllustrations) => updateRoleAssetOrganization(categories, bindings, removedIllustrations)}
      onRemoveRoleAsset={(path) => void removeRoleAsset(path)}
      onImportRolePetPackage={() => void importRolePetPackage()}
      onRemoveRolePetPackage={(packageId) => void removeRolePetPackage(packageId)}
      onSelectRolePetPackage={(packageId) => void selectRolePetPackage(packageId)}
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
      canRegenerateLightboxImage={Boolean(activeSessionKey && selectedChatImageEntry?.messageId)}
      addingChatImageToAssetLibrary={addingChatImageToAssetLibrary}
      regeneratingSelectedChatImage={regeneratingSelectedChatImage}
      chatImageLightboxOpen={chatImageLightboxOpen}
      onAddSelectedChatImageToAssetLibrary={() => void addSelectedChatImageToAssetLibrary()}
      onCloseSelectedChatImageLightbox={closeSelectedChatImageLightbox}
      onLocateSelectedChatImageMessage={locateSelectedChatImageMessage}
      onRegenerateSelectedChatImage={() => void regenerateSelectedChatImage()}
    />
  );
}

registerRendererGlobalDiagnostics();

createRoot(document.getElementById("root") as HTMLElement).render(
  <DesktopErrorBoundary>
    <App />
  </DesktopErrorBoundary>,
);
