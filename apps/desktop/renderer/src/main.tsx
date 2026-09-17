import { PluginChatImageActions } from "./plugins/PluginChatImageActions";
import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { DesktopAppFrame } from "./app/DesktopAppFrame";
import {
  chatLatestImageSidebarDefaultWidth,
  chatLatestImageSidebarMaxWidth,
  chatLatestImageSidebarMinWidth,
  createEmptyRoleForm,
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
import type { RoleSessionCache } from "./chat/roleSessionCache";
import type { ChatMessageNavigationScroller } from "./chat/useChatScrollController";
import { DesktopErrorBoundary } from "./diagnostics/DesktopErrorBoundary";
import { registerRendererGlobalDiagnostics } from "./diagnostics/rendererGlobalDiagnostics";
// Registers every plugin's compiled-in settings.section/nav.page contributions
// into pluginUiRegistry before any component (nav rail, settings sidebar) reads it.
import "./plugins/pluginUiModules";
import { initializeRuntimePluginUi } from "./plugins/runtimePluginUiBootstrap";
import { createRoleFormFromRole } from "./roles/roleFormState";
import { type RoleWorkspaceSectionId } from "./roles/RoleWorkspaceSidebar";
import { useRoleFormAdapters } from "./roles/useRoleFormAdapters";
import { type SettingsSectionId } from "./settings/SettingsSidebar";
import { useSettingsSubsectionMemory } from "./settings/useSettingsSubsectionMemory";
import { useLatestRef } from "./shared/useLatestRef";
import { useLeftSidebarState } from "./shared/useLeftSidebarState";
import { useRightSidebarState } from "./shared/useRightSidebarState";
import type {
  AppMainView,
  PendingRoleCardAction,
  RoleRecord,
  SessionImageHistoryMessage,
  SessionPayload,
} from "./shared/types";
import "./styles.css";
import { useOnboardingController } from "./onboarding/useOnboardingController";
import { OnboardingPage } from "./onboarding/OnboardingPage";

function App(): React.ReactElement {
  const [health, setHealth] = useState("connecting");
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
  // Own lifetime, separate from `workspaceFeedback` on purpose (issue #226
  // follow-up): that one is gated to the role-workspace view and cleared by
  // that flow's own state transitions, so relaxing its gate would let a
  // stale role-workspace message follow the user into an unrelated view. A
  // refused nav.page selection (`guardedNavPageSelect`) can happen from any
  // view, so it gets its own slot, auto-cleared the same way `notice`/
  // `workspaceFeedback` already are (see `useDesktopUiEffects`).
  const [navBlockedMessage, setNavBlockedMessage] = useState("");
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
  // The last active subtab per settings section id (issue #230 AC 4), lifted
  // here alongside `settingsSection` so it survives a section swap that
  // would otherwise unmount SettingsPage's own internal state; owned by
  // useSettingsSubsectionMemory (see its doc comment), not raw state here,
  // so navigation history and SettingsPage share one resolve/remember
  // implementation instead of each reaching into the record separately.
  const settingsSubsectionMemory = useSettingsSubsectionMemory();
  const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({});
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
  const pendingMessageNavigationRef = useLatestRef(pendingMessageNavigation);
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
  const roleWorkspaceSection: RoleWorkspaceSectionId =
    mainView.kind === "role-create"
      ? "role-create"
      : mainView.kind === "role-assets"
        ? "role-assets"
        : mainView.kind === "role-detail"
        ? "role-detail"
        : "roles-list";
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
    setHighlightedMessageKey(nextMessageKey);
  }

  function clearMessageNavigation(target?: { roleId: string; messageKey: string }): void {
    const current = pendingMessageNavigationRef.current;
    if (
      target
      && (!current || current.roleId !== target.roleId || current.messageKey !== target.messageKey)
    ) {
      return;
    }
    setPendingMessageNavigation(null);
    setHighlightedMessageKey("");
  }

  const handleMessageNavigationTargetMounted = useCallback((
    messageKey: string,
    target: HTMLElement,
    scrollToMessage: ChatMessageNavigationScroller,
  ): void => {
    const current = pendingMessageNavigationRef.current;
    if (
      !current
      || current.roleId !== activeRoleIdRef.current
      || current.messageKey !== messageKey
    ) {
      return;
    }
    scrollToMessage(target, () => {
      const latest = pendingMessageNavigationRef.current;
      if (
        !latest
        || latest.roleId !== activeRoleIdRef.current
        || latest.messageKey !== messageKey
      ) {
        return;
      }
      setPendingMessageNavigation(null);
      setHighlightedMessageKey("");
    });
  }, [activeRoleIdRef, pendingMessageNavigationRef]);

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
    openSettingsWorkspace,
    updateSettingsSubsection,
    openRoleWorkspace,
    openPluginPage,
    navigateHistory,
    pushNavigationEntry,
  } = useNavigationHistory({
    mainView,
    settingsSection,
    settingsSubsectionMemory,
    activeRoleIdRef,
    lastNonSettingsViewRef,
    roles,
    setSettingsSection,
    setSidebarAnimating: leftSidebar.setAnimating,
    setSidebarCollapsed: leftSidebar.setCollapsed,
    setSidebarWidth: leftSidebar.setWidth,
    setMainView,
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

  const bridgeLifecycle = useDesktopBridgeLifecycle({
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
    applyPluginImageUpdate,
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
    refreshDetailRoleForPlugins,
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
    pendingMessageNavigation,
    setHighlightedMessageKey,
    notice,
    setNotice,
    workspaceFeedback,
    setWorkspaceFeedback,
    navBlockedMessage,
    setNavBlockedMessage,
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

  const onboarding = useOnboardingController(openRole, bridgeLifecycle);
  if (onboarding.visible) {
    return <OnboardingPage controller={onboarding} windowMaximized={windowMaximized} />;
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
      shellResizing={leftSidebar.resizing || chatLatestImageSidebar.resizing}
      sidebarState={{
        collapsed: leftSidebar.collapsed,
        width: leftSidebar.width,
        animating: leftSidebar.animating,
        resizing: leftSidebar.resizing,
        onBeginResize: leftSidebar.beginResize,
      }}
      mainView={mainView}
      settingsSection={settingsSection}
      activeSettingsSubsections={settingsSubsectionMemory.activeSubsections}
      onChangeSettingsSubsection={updateSettingsSubsection}
      onBackToChat={() => openChatView()}
      onOpenSettingsSection={(section) => openSettingsWorkspace(section)}
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
      onOpenPluginPage={(pageId) => openPluginPage(pageId)}
      navBlockedMessage={navBlockedMessage}
      onNavigationBlocked={(message) => setNavBlockedMessage(message)}
      onOpenRole={(roleId) => void openRole(roleId, null, { recordHistory: true })}
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
      onMessageNavigationTargetMounted={handleMessageNavigationTargetMounted}
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
      roleCardImport={roleCreation.roleCardImport}
      onPreviewRoleCard={() => void roleCreation.previewRoleCard()}
      onCancelRoleCardImport={() => void roleCreation.cancelRoleCardImport()}
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
      onPluginRoleDataChanged={() => void refreshDetailRoleForPlugins()}
      onSelectAvatarAsset={setSelectedAvatarAsset}
      onSelectChatBackground={setSelectedChatBackground}
      onSaveRoleAssets={(nextSelection) => void saveRoleAssets(nextSelection)}
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
          clearMessageNavigation,
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
      chatImageActions={selectedChatImageEntry ? <PluginChatImageActions
        target={{ ...selectedChatImageEntry, sessionKey: activeSessionKey }}
        onSessionUpdate={applyPluginImageUpdate} onError={setError} onNotice={setNotice}
      /> : null}
      canLocateLightboxMessage={Boolean(activeRoleId && selectedChatImageEntry?.messageId)}
      addingChatImageToAssetLibrary={addingChatImageToAssetLibrary}
      chatImageLightboxOpen={chatImageLightboxOpen}
      onAddSelectedChatImageToAssetLibrary={() => void addSelectedChatImageToAssetLibrary()}
      onCloseSelectedChatImageLightbox={closeSelectedChatImageLightbox}
      onLocateSelectedChatImageMessage={locateSelectedChatImageMessage}
    />
  );
}

registerRendererGlobalDiagnostics();

initializeRuntimePluginUi();
createRoot(document.getElementById("root") as HTMLElement).render(
  <DesktopErrorBoundary>
    <App />
  </DesktopErrorBoundary>,
);
