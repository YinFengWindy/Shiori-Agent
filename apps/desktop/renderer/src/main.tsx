import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { DesktopAppFrame } from "./app/DesktopAppFrame";
import {
  chatLatestImageSidebarDefaultWidth,
  chatLatestImageSidebarMaxWidth,
  chatLatestImageSidebarMinWidth,
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
import { useRoleCreationController } from "./app/useRoleCreationController";
import { useRoleSearch } from "./app/roleSearch";
import { navigateToRoleSearchResult } from "./app/roleSearchNavigation";
import { buildDesktopViewModel } from "./app/desktopSelectors";
import { useRolePresentation } from "./app/useRolePresentation";
import { useStoryWorkspacePresentation } from "./app/useStoryWorkspacePresentation";
import type { RoleSessionCache } from "./chat/roleSessionCache";
import { DesktopErrorBoundary } from "./diagnostics/DesktopErrorBoundary";
import { registerRendererGlobalDiagnostics } from "./diagnostics/rendererGlobalDiagnostics";
import { useImageStudioState } from "./image/useImageStudioState";
import { type PromptTagWorkspaceSectionId } from "./image/PromptTagWorkspaceSidebar";
import { createRoleFormFromRole, syncRoleFormMoodConfig } from "./roles/roleFormState";
import { useRoleDifferenceGeneration } from "./roles/useRoleDifferenceGeneration";
import { type RoleWorkspaceSectionId } from "./roles/RoleWorkspaceSidebar";
import { useRoleFormAdapters } from "./roles/useRoleFormAdapters";
import { type SettingsSectionId } from "./settings/SettingsSidebar";
import { useLatestRef } from "./shared/useLatestRef";
import { useLeftSidebarState } from "./shared/useLeftSidebarState";
import { useRightSidebarState } from "./shared/useRightSidebarState";
import { createStoryBridgeClient } from "./story/storyBridgeClient";
import { useStoryController } from "./story/useStoryController";
import { StoryAppSurface } from "./story/StoryAppSurface";
import type {
  AppMainView,
  PendingRoleCardAction,
  RoleRecord,
  SessionImageHistoryMessage,
  SessionPayload,
} from "./shared/types";
import "./styles.css";

type StoryRouteProps = {
  roles: RoleRecord[];
  onExit: () => void;
};

/** Mounts Story bridge and presentation state only while its route is active. */
function StoryRoute({ roles, onExit }: StoryRouteProps): React.ReactElement {
  const storyBridgeClient = useMemo(() => createStoryBridgeClient(), []);
  const storyController = useStoryController(storyBridgeClient);
  const storyPresentation = useStoryWorkspacePresentation({
    roles,
    client: storyBridgeClient,
    controller: storyController,
    onExit,
  });

  return <StoryAppSurface>{storyPresentation.content}</StoryAppSurface>;
}

function App(): React.ReactElement {
  const [health, setHealth] = useState("connecting");
  const [promptTagWorkspaceSection, setPromptTagWorkspaceSection] = useState<PromptTagWorkspaceSectionId>("list");
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [activeRoleId, setActiveRoleId] = useState("");
  const [activeSession, setActiveSession] = useState<SessionPayload | null>(null);
  const [, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [savingRole, setSavingRole] = useState(false);
  const [savingRoleAssets, setSavingRoleAssets] = useState(false);
  const [deletingRole, setDeletingRole] = useState(false);
  // Track in-flight chat turns by session so role switches don't leak typing state into other chats.
  const [sendingSessions, setSendingSessions] = useState<Record<string, string>>({});
  const [cancellingSessions, setCancellingSessions] = useState<Record<string, string>>({});
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
  const [settingsSection, setSettingsSection] = useState<SettingsSectionId>("models");
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
  const [imageHistoryMessages, setImageHistoryMessages] = useState<SessionImageHistoryMessage[]>([]);
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
  const cancellingSessionsRef = useLatestRef(cancellingSessions);
  const unreadCountsRef = useLatestRef(unreadCounts);
  const roleFormRef = useLatestRef(roleForm);
  const imageHistorySessionKeyRef = useRef("");
  const activeSessionKeyForImages = activeSession?.key ?? "";
  const activeSessionUpdatedAtForImages = activeSession?.updated_at ?? "";
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
  const { updateRoleForm } = useRoleFormAdapters({
    roleFormRef,
    setRoleForm,
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
    openStoryWorkspace,
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
    cancelChatTurn,
    completeChatTurn,
    isCurrentChatTurn,
    isChatTurnCancelling,
    appendSessionErrorMessage,
    openRole,
    sendMessage,
    loadOlderMessages,
    loadMessagesAround,
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
    setCancellingSessions,
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
    cancellingSessionsRef,
    unreadCountsRef,
    openRoleRequestIdRef,
  });

  useEffect(() => {
    const sessionKey = activeSessionKeyForImages;
    if (!sessionKey) {
      setImageHistoryMessages([]);
      imageHistorySessionKeyRef.current = "";
      return;
    }
    const sessionChanged = imageHistorySessionKeyRef.current !== sessionKey;
    imageHistorySessionKeyRef.current = sessionKey;
    // Do not expose the previous role's media while the new index is loading.
    if (sessionChanged) setImageHistoryMessages([]);
    let cancelled = false;
    void window.miraDesktop.invoke({
      method: "session.imageHistory",
      payload: { session_key: sessionKey },
    }).then((response) => {
      if (cancelled || response.error) return;
      if (response.payload.session_key !== sessionKey) return;
      const messages = response.payload.messages;
      if (!Array.isArray(messages)) return;
      setImageHistoryMessages(messages.filter((message): message is SessionImageHistoryMessage => (
        Boolean(message) && typeof message === "object"
        && typeof (message as { id?: unknown }).id === "string"
        && typeof (message as { seq?: unknown }).seq === "number"
        && Array.isArray((message as { media?: unknown }).media)
      )));
    });
    return () => {
      cancelled = true;
    };
  }, [activeSessionKeyForImages, activeSessionUpdatedAtForImages]);

  useDesktopBridgeLifecycle({
    activeRoleId,
    activeIllustration,
    setActiveRoleId,
    setActiveIllustration,
    setHealth,
    setError,
    setNotice,
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
    isVisibleChatCancelling,
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
    imageHistoryMessages,
    selectedChatImageKey,
    health,
    sendingSessions,
    cancellingSessions,
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
    loadMessagesAround,
    queueMessageNavigation,
    setError,
    setNotice,
  });

  const roleCreation = useRoleCreationController({
    activeRoleIdRef,
    setPendingRoleCardAction,
    setWorkspaceFeedback,
    setError,
    setRoles,
    setActiveRoleId,
    openRoleWorkspace,
    buildNavigationEntry,
    replaceNavigationEntry,
    loadRolesFromBridge,
    openRole,
    applyRoleSnapshot,
  });

  const {
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

  const roleDifferenceGeneration = useRoleDifferenceGeneration({
    roleId: detailRoleId,
    onRoleUpdated: (updated) => {
      setRoles((current) => current.map((role) => role.id === updated.id ? updated : role));
      if (updated.id === detailRoleId) {
        updateRoleForm((current) => syncRoleFormMoodConfig(current, updated));
        applyRoleSnapshot(updated);
        setNotice("角色差分已生成并加入素材库。");
      }
    },
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

  async function resetRoleForm(): Promise<void> {
    if (!detailRole) return;
    updateRoleForm(createRoleFormFromRole(detailRole));
    setNotice("角色表单已重置。");
  }

  if (mainView.kind === "story") {
    return <StoryRoute roles={roles} onExit={() => openChatView()} />;
  }

  return (
    <DesktopAppFrame
      sidebarCollapsed={leftSidebar.collapsed}
      windowMaximized={windowMaximized}
      canGoBack={canGoBack}
      canGoForward={canGoForward}
      canRefreshSession={mainView.kind === "chat" && Boolean(activeRoleId)}
      onToggleSidebar={leftSidebar.toggle}
      onGoBack={() => void navigateHistory("back", openRole)}
      onGoForward={() => void navigateHistory("forward", openRole)}
      onRefreshSession={() => void refreshSession()}
      onOpenSettings={() => openSettingsWorkspace()}
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
      onOpenStory={() => openStoryWorkspace()}
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
      isVisibleChatCancelling={isVisibleChatCancelling}
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
      onCancelChat={() => void cancelChatTurn(activeSessionKey, activeRoleId)}
      onLoadOlderMessages={loadOlderMessages}
      imageHistorySidebar={imageHistorySidebar}
      detailRole={detailRole}
      pendingRoleCardAction={pendingRoleCardAction}
      onOpenRoleManagementDetail={(roleId) => void openRoleDetail(roleId)}
      onRequestDeleteRole={setPendingDeleteRoleId}
      creating={roleCreation.creating}
      newRoleForm={roleCreation.newRoleForm}
      onBackToRoleList={roleCreation.cancelCreateRole}
      onCreateNewRole={() => void roleCreation.createRole()}
      onResetNewRoleForm={roleCreation.resetNewRoleForm}
      onUpdateNewRoleForm={roleCreation.updateNewRoleForm}
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
      differenceGeneration={roleDifferenceGeneration.state}
      onGenerateDifferences={(baseAsset) => void roleDifferenceGeneration.generate(baseAsset)}
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
        const messageKey = result.matchedField === "message"
          ? getMessageKey(result.matchedMessageId)
          : "";
        void navigateToRoleSearchResult({
          result,
          messageKey,
          openChatView,
          isSearchResultSessionActive: (roleId, sessionKey) => (
            activeRoleIdRef.current === roleId && activeSessionRef.current?.key === sessionKey
          ),
          queueMessageNavigation,
          clearMessageNavigation: () => {
            setPendingMessageNavigation(null);
            setHighlightedMessageKey("");
          },
          openRole: (roleId, options) => openRole(roleId, null, options),
          loadMessagesAround,
        });
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
