import type React from "react";
import { ChatImageLightbox } from "../chat/ChatImageLightbox";
import { ChatSurface } from "../chat/ChatSurface";
import type { ChatMessageNavigationScroller } from "../chat/useChatScrollController";
import { guardedNavPageSelect } from "../plugins/pluginUiRegistry";
import { BridgeOfflineBanner } from "./BridgeOfflineBanner";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { RoleAssetsPage } from "../roles/RoleAssetsPage";
import { RoleCreatePage } from "../roles/RoleCreatePage";
import { RoleDetailPage } from "../roles/RoleDetailPage";
import { RoleManagementPage } from "../roles/RoleManagementPage";
import { RoleSearchDialog } from "../roles/RoleSearchDialog";
import type { RoleWorkspaceSectionId } from "../roles/RoleWorkspaceSidebar";
import { SidebarTrackContent, type SidebarViewState } from "./SidebarTrackContent";
import { previewFromSessionMessages } from "../roles/roleChatPreview";
import { usePluginUiVisibility } from "./usePluginUiVisibility";
import { SettingsPage } from "../settings/SettingsPage";
import { type SettingsSectionId } from "../settings/SettingsSidebar";
import { cx, sidebarTrackMotionClass } from "../shared/styles";
import { buildNavRailViews, NavRail, pluginNavRailViewId, type NavRailViewId } from "../shell/NavRail";
import { useGlobalShortcuts } from "../shell/useGlobalShortcuts";
import type {
  AppMainView,
  ChatSendRequest,
  NewRoleFormState,
  PendingRoleCardAction,
  RoleFormState,
  RoleRecord,
  RoleSearchResult,
  SessionPayload,
} from "../shared/types";
import type { RoleCardImportState } from "./roleCardImportState";
import { TitleBar } from "../shell/TitleBar";

type RightSidebarViewState = {
  collapsed: boolean;
  width: number;
  animating: boolean;
  resizing: boolean;
  beginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
  toggle: () => void;
};

type DesktopAppFrameProps = {
  sidebarCollapsed: boolean;
  windowMaximized: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  canRefreshSession: boolean;
  onToggleSidebar: () => void;
  onGoBack: () => void;
  onGoForward: () => void;
  onRefreshSession: () => void;
  onOpenSettings: () => void;
  shellResizing: boolean;
  sidebarState: SidebarViewState;
  mainView: AppMainView;
  settingsSection: SettingsSectionId;
  /** The last active subtab per settings section id (issue #230 AC 4) — see `useNavigationHistory`. */
  activeSettingsSubsections: Record<string, string>;
  onChangeSettingsSubsection: (sectionId: string, subsectionId: string) => void;
  onBackToChat: () => void;
  onOpenSettingsSection: (section: SettingsSectionId) => void;
  roleWorkspaceViewActive: boolean;
  roleWorkspaceSection: RoleWorkspaceSectionId;
  onOpenRoleWorkspaceSection: (section: RoleWorkspaceSectionId) => void;
  roles: RoleRecord[];
  activeRoleId: string;
  unreadCounts: Record<string, number>;
  bridgeReady: boolean;
  onOpenSearch: () => void;
  onOpenRolesWorkspace: () => void;
  onOpenPluginPage: (pageId: string) => void;
  onOpenRole: (roleId: string) => void;
  /** Raw bridge health ("connecting" / "online" / "offline"); drives the offline banner. */
  health: string;
  bridgeError: string;
  onRestartBridge: () => Promise<void>;
  activeRole: RoleRecord | null;
  activeSession: SessionPayload | null;
  chatLatestImagePath: string;
  chatLatestImagePosition: number;
  chatLatestImageSidebar: RightSidebarViewState;
  chatLatestImageSidebarCount: number;
  currentMood: string;
  moodIllustrationUrl: string;
  /** When the session last set the mood (`current_mood_updated_at`). */
  moodUpdatedAt: string;
  roleSelfView: string;
  relationshipTags: string[];
  lonelinessValue: number;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  headerTitle: string;
  highlightedMessageKey: string;
  onMessageNavigationTargetMounted?: (
    messageKey: string,
    target: HTMLElement,
    scrollToMessage: ChatMessageNavigationScroller,
  ) => void;
  isVisibleChatSending: boolean;
  isVisibleChatCancelling: boolean;
  visibleIllustrationUrl: string;
  windowVisible: boolean;
  onGoToNextChatImage: () => void;
  onGoToPreviousChatImage: () => void;
  onOpenChatImageLightbox: () => void;
  onOpenChatImagePreview: (target: { historyKey: string }) => void;
  onOpenRoleDetail: () => void;
  onJumpToMessage: (messageKey: string) => void;
  onBeginAttachmentDrag: (path: string) => void;
  onCopyMessage: (content: string) => void;
  onSendMessage: (request: ChatSendRequest) => Promise<boolean>;
  onCancelChat: () => void;
  /** Re-sends the user message of the failed turn ending in this error row. */
  onRetryFailedTurn: (errorKey: string) => void;
  onLoadOlderMessages: (sessionKey: string) => Promise<boolean>;
  detailRole: RoleRecord | null;
  pendingRoleCardAction: PendingRoleCardAction;
  onOpenRoleManagementDetail: (roleId: string) => void;
  /** Leaves role detail for the chat with that role. */
  onGoToRoleChat: (roleId: string) => void;
  /** Starts a role card import from the role workspace sidebar. */
  onImportRoleCard: () => void;
  onRequestDeleteRole: (roleId: string) => void;
  creating: boolean;
  newRoleForm: NewRoleFormState;
  onBackToRoleList: () => void;
  onCreateNewRole: () => void;
  onResetNewRoleForm: () => void;
  onUpdateNewRoleForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
  roleCardImport: RoleCardImportState;
  onPreviewRoleCard: () => void;
  onCancelRoleCardImport: () => void;
  detailRoleId: string;
  previewAvatar: string | null;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onOpenAssetsPage: () => void;
  /** Opens 设置 › 插件, on the plugin's own settings tab when given (role detail channel notices). */
  onOpenPluginSettings: (pluginId: string | null) => void;
  /** A role's model binding changed outside the draft (role detail 模型 section). */
  onRoleModelChanged: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
  savingRoleAssets: boolean;
  selectedAvatarAsset: string;
  selectedChatBackground: string;
  onBackToRoleDetail: () => void;
  onPickRoleAssets: (categoryId: string) => void;
  onUpdateRoleAssetOrganization: (categories: import("../shared/types").RoleAssetCategory[], bindings: Record<string, string>, removedIllustrations?: string[]) => Promise<boolean>;
  onRemoveRoleAsset: (path: string) => void;
  onPluginRoleDataChanged: () => void;
  onSelectAvatarAsset: (path: string) => void;
  onSelectChatBackground: (path: string) => void;
  onSaveRoleAssets: (nextSelection?: { avatarAsset?: string; chatBackground?: string; moodIllustrationBindings?: Record<string, string> }) => void;
  showSearchDialog: boolean;
  searchQuery: string;
  searchingSessions: boolean;
  searchResults: RoleSearchResult[];
  onCloseSearchDialog: () => void;
  onSelectSearchResult: (result: RoleSearchResult) => void;
  onUpdateSearchQuery: (value: string) => void;
  pendingDeleteRole: RoleRecord | null;
  deletingRole: boolean;
  onCloseDeleteDialog: () => void;
  onConfirmDeleteRole: () => void;
  canAddToAssetLibrary: boolean;
  canGoToNextLightboxImage: boolean;
  canGoToPreviousLightboxImage: boolean;
  canLocateLightboxMessage: boolean;
  chatImageActions: React.ReactNode;
  addingChatImageToAssetLibrary: boolean;
  chatImageLightboxOpen: boolean;
  onAddSelectedChatImageToAssetLibrary: () => void;
  onCloseSelectedChatImageLightbox: () => void;
  onLocateSelectedChatImageMessage: () => void;
  /** Unsaved-role-edits guard (see `useLeaveGuard`): a held-back navigation waiting for the user. */
  leaveConfirmOpen: boolean;
  leaveRoleName: string;
  onConfirmLeave: () => void;
  onCancelLeave: () => void;
};

/** Renders the desktop shell around the already-prepared application state. */
export function DesktopAppFrame({
  sidebarCollapsed,
  windowMaximized,
  canGoBack,
  canGoForward,
  canRefreshSession,
  onToggleSidebar,
  onGoBack,
  onGoForward,
  onRefreshSession,
  onOpenSettings,
  shellResizing,
  sidebarState,
  mainView,
  settingsSection,
  activeSettingsSubsections,
  onChangeSettingsSubsection,
  onBackToChat,
  onOpenSettingsSection,
  roleWorkspaceViewActive,
  roleWorkspaceSection,
  onOpenRoleWorkspaceSection,
  roles,
  activeRoleId,
  unreadCounts,
  bridgeReady,
  onOpenSearch,
  onOpenRolesWorkspace,
  onOpenPluginPage,
  onOpenRole,
  health,
  bridgeError,
  onRestartBridge,
  activeRole,
  activeSession,
  chatLatestImagePath,
  chatLatestImagePosition,
  chatLatestImageSidebar,
  chatLatestImageSidebarCount,
  currentMood,
  moodIllustrationUrl,
  moodUpdatedAt,
  roleSelfView,
  relationshipTags,
  lonelinessValue,
  conversationEndRef,
  headerTitle,
  highlightedMessageKey,
  onMessageNavigationTargetMounted,
  isVisibleChatSending,
  isVisibleChatCancelling,
  visibleIllustrationUrl,
  windowVisible,
  onGoToNextChatImage,
  onGoToPreviousChatImage,
  onOpenChatImageLightbox,
  onOpenChatImagePreview,
  onOpenRoleDetail,
  onJumpToMessage,
  onBeginAttachmentDrag,
  onCopyMessage,
  onSendMessage,
  onCancelChat,
  onRetryFailedTurn,
  onLoadOlderMessages,
  detailRole,
  pendingRoleCardAction,
  onOpenRoleManagementDetail,
  onGoToRoleChat,
  onImportRoleCard,
  onRequestDeleteRole,
  creating,
  newRoleForm,
  onBackToRoleList,
  onCreateNewRole,
  onResetNewRoleForm,
  onUpdateNewRoleForm,
  roleCardImport,
  onPreviewRoleCard,
  onCancelRoleCardImport,
  detailRoleId,
  previewAvatar,
  roleForm,
  roleFormDirty,
  savingRole,
  onOpenAssetsPage,
  onOpenPluginSettings,
  onRoleModelChanged,
  onUpdateRoleForm,
  onResetRoleForm,
  onSaveRole,
  savingRoleAssets,
  selectedAvatarAsset,
  selectedChatBackground,
  onBackToRoleDetail,
  onPickRoleAssets,
  onUpdateRoleAssetOrganization,
  onRemoveRoleAsset,
  onPluginRoleDataChanged,
  onSelectAvatarAsset,
  onSelectChatBackground,
  onSaveRoleAssets,
  showSearchDialog,
  searchQuery,
  searchingSessions,
  searchResults,
  onCloseSearchDialog,
  onSelectSearchResult,
  onUpdateSearchQuery,
  pendingDeleteRole,
  deletingRole,
  onCloseDeleteDialog,
  onConfirmDeleteRole,
  canAddToAssetLibrary,
  canGoToNextLightboxImage,
  canGoToPreviousLightboxImage,
  canLocateLightboxMessage,
  chatImageActions,
  addingChatImageToAssetLibrary,
  chatImageLightboxOpen,
  onAddSelectedChatImageToAssetLibrary,
  onCloseSelectedChatImageLightbox,
  onLocateSelectedChatImageMessage,
  leaveConfirmOpen,
  leaveRoleName,
  onConfirmLeave,
  onCancelLeave,
}: DesktopAppFrameProps) {
  const navRailActiveView: NavRailViewId | null = mainView.kind === "chat"
    ? "messages"
    : roleWorkspaceViewActive
      ? "roles"
      : mainView.kind === "settings"
          ? "settings"
          : mainView.kind === "plugin-page"
            ? pluginNavRailViewId(mainView.pageId)
            : null;
  const navRailUnreadTotal = Object.values(unreadCounts).reduce((total, count) => total + count, 0);
  // nav.page entries are compiled in statically (see pluginUiModules.ts); listed here
  // rather than threaded through props, matching how this frame already owns view
  // dispatch and keeps the (already very large) prop surface from growing further.
  // Visibility (hiding a disabled plugin's entries immediately, issue #174 AC 3)
  // is centralized in usePluginUiVisibility so it isn't recomputed per call site.
  const { pluginNavPages, settingsSidebarSections, isSectionVisible, resolveVisibleNavPage, isPluginEnabled } = usePluginUiVisibility();
  const activePluginNavPage = mainView.kind === "plugin-page"
    ? resolveVisibleNavPage(mainView.pageId)
    : undefined;
  const fullscreenPluginActive = activePluginNavPage?.presentation === "fullscreen";
  // Shared by the role sidebar and the empty role grid: an import needs the bridge and no import/create in flight.
  const canImportRoleCard = bridgeReady && !creating && roleCardImport.status === "idle";
  const navRailViews = buildNavRailViews({
    onBackToChat,
    onOpenRolesWorkspace,
    pluginEntries: pluginNavPages.map((page) => ({
      pageId: page.id,
      label: page.label,
      icon: page.icon,
      onSelect: guardedNavPageSelect(page, () => onOpenPluginPage(page.id), (message) => feedback.warning(message)),
    })),
  });
  // A full-window plugin surface (story) owns its own keys, including leaving.
  useGlobalShortcuts({
    enabled: !fullscreenPluginActive,
    onSearch: onOpenSearch,
    onSettings: onOpenSettings,
    views: navRailViews,
  });

  if (activePluginNavPage && fullscreenPluginActive) {
    return <activePluginNavPage.Component pageId={activePluginNavPage.id} activeRoleId={activeRoleId} onExit={onBackToChat} />;
  }

  return (
    <div className="app-frame grid h-screen grid-rows-app overflow-hidden bg-transparent">
      <TitleBar
        sidebarCollapsed={sidebarCollapsed}
        windowMaximized={windowMaximized}
        canGoBack={canGoBack}
        canGoForward={canGoForward}
        canRefreshSession={canRefreshSession}
        onToggleSidebar={onToggleSidebar}
        onGoBack={onGoBack}
        onGoForward={onGoForward}
        onRefreshSession={onRefreshSession}
      />
      <div>
        <BridgeOfflineBanner health={health} bridgeError={bridgeError} onRestart={onRestartBridge} />
      </div>
      <div
        className={cx(
          "desktop-shell grid min-h-0 overflow-hidden bg-transparent",
          shellResizing && "sidebar-resizing cursor-col-resize select-none",
        )}
        style={{
          gridTemplateColumns: "52px minmax(0, auto) minmax(0, 1fr)",
        }}
      >
        <NavRail
          activeView={navRailActiveView}
          unreadTotal={navRailUnreadTotal}
          views={navRailViews}
          onOpenSearch={onOpenSearch}
          onOpenSettings={onOpenSettings}
        />
        <div
          className={cx(
            "sidebar-track relative min-h-0",
            // Compact: the track takes no width and its content floats over the main pane.
            sidebarState.compact ? "z-20 overflow-visible" : "overflow-hidden",
            sidebarState.animating && !sidebarState.compact && sidebarTrackMotionClass,
          )}
          style={{ width: sidebarState.compact || sidebarState.collapsed ? 0 : sidebarState.width }}
          data-testid="sidebar-track"
          data-compact={sidebarState.compact || undefined}
        >
          {sidebarState.compact ? (
            <div
              className={cx(
                "sidebar-overlay-surface surface-glass-strong absolute inset-y-0 left-0 rounded-r-lg transition-opacity duration-base ease-out-soft",
                sidebarState.collapsed ? "pointer-events-none opacity-0" : "opacity-100",
              )}
              style={{ width: sidebarState.width }}
              aria-hidden="true"
            />
          ) : null}
          {/* A closed compact overlay must not keep its footprint clickable: its
              content is pointer-events-none, so hit-testing would land on this
              wrapper and swallow clicks meant for the chat underneath. */}
          <div className={cx("h-full", sidebarState.compact && "absolute inset-y-0 left-0", sidebarState.compact && sidebarState.collapsed && "pointer-events-none")}>
          <SidebarTrackContent
            mainView={mainView}
            sidebarState={sidebarState}
            settingsSection={settingsSection}
            settingsSidebarSections={settingsSidebarSections}
            onOpenSettingsSection={onOpenSettingsSection}
            roleWorkspaceViewActive={roleWorkspaceViewActive}
            roleWorkspaceSection={roleWorkspaceSection}
            onOpenRoleWorkspaceSection={onOpenRoleWorkspaceSection}
            roleWorkspaceRoleId={mainView.kind === "role-detail" || mainView.kind === "role-assets" ? mainView.roleId : ""}
            pendingRoleId={pendingRoleCardAction?.roleId ?? ""}
            canImportRoleCard={canImportRoleCard}
            onOpenRoleDetail={onOpenRoleManagementDetail}
            onImportRoleCard={onImportRoleCard}
            roles={roles}
            activeRoleId={activeRoleId}
            unreadCounts={unreadCounts}
            activeRolePreview={previewFromSessionMessages(activeSession?.messages ?? [])}
            bridgeReady={bridgeReady}
            onOpenRole={onOpenRole}
            activePluginNavPage={activePluginNavPage}
          />
          </div>
        </div>
        <main className="chat-pane relative grid min-h-0 grid-cols-[minmax(0,1fr)] overflow-hidden rounded-l-lg border-b border-l border-t border-line-soft bg-[var(--chat-bg)] shadow-soft">
          {sidebarState.compact && !sidebarState.collapsed ? (
            <button
              className="motion-fade-enter absolute inset-0 z-[19] cursor-default border-0 bg-white/25 p-0"
              type="button"
              aria-label="收起侧边栏"
              tabIndex={-1}
              onClick={onToggleSidebar}
            />
          ) : null}
          {sidebarState.collapsed && !sidebarState.compact ? (
            <div
              className="absolute inset-y-0 left-0 z-[7] w-[3px] cursor-col-resize transition-colors hover:bg-accent-soft"
              role="separator"
              aria-orientation="vertical"
              aria-label="拖拽展开侧边栏"
              onPointerDown={sidebarState.onBeginResize}
            />
          ) : null}
          {mainView.kind === "chat" ? (
            <ChatSurface
              activeRole={activeRole}
              activeRoleId={activeRoleId}
              activeSession={activeSession}
              bridgeReady={bridgeReady}
              chatLatestImagePath={chatLatestImagePath}
              chatLatestImagePosition={chatLatestImagePosition}
              chatLatestImageSidebarAnimating={chatLatestImageSidebar.animating}
              chatLatestImageSidebarResizing={chatLatestImageSidebar.resizing}
              chatLatestImageSidebarCollapsed={chatLatestImageSidebar.collapsed}
              chatLatestImageSidebarCount={chatLatestImageSidebarCount}
              chatLatestImageSidebarWidth={chatLatestImageSidebar.width}
              currentMood={currentMood}
              moodIllustrationUrl={moodIllustrationUrl}
              moodUpdatedAt={moodUpdatedAt}
              roleSelfView={roleSelfView}
              relationshipTags={relationshipTags}
              lonelinessValue={lonelinessValue}
              conversationEndRef={conversationEndRef}
              headerTitle={headerTitle}
              highlightedMessageKey={highlightedMessageKey}
              onMessageNavigationTargetMounted={onMessageNavigationTargetMounted}
              sending={isVisibleChatSending}
              cancelling={isVisibleChatCancelling}
              visibleIllustrationUrl={visibleIllustrationUrl}
              windowVisible={windowVisible}
              onBeginChatLatestImageSidebarResize={chatLatestImageSidebar.beginResize}
              onGoToNextChatImage={onGoToNextChatImage}
              onGoToPreviousChatImage={onGoToPreviousChatImage}
              onOpenChatImageLightbox={onOpenChatImageLightbox}
              onOpenChatImagePreview={onOpenChatImagePreview}
              onOpenRoleDetail={onOpenRoleDetail}
              onJumpToMessage={onJumpToMessage}
              onBeginAttachmentDrag={onBeginAttachmentDrag}
              onCopyMessage={onCopyMessage}
              onSendMessage={onSendMessage}
              onCancelChat={onCancelChat}
              onRetryFailedTurn={onRetryFailedTurn}
              onLoadOlderMessages={onLoadOlderMessages}
              onToggleChatLatestImageSidebar={chatLatestImageSidebar.toggle}
            />
          ) : null}
          {mainView.kind === "roles-list" ? (
            <RoleManagementPage
              activeRoleId={activeRoleId}
              bridgeReady={bridgeReady}
              canImportRoleCard={canImportRoleCard}
              pendingCardAction={pendingRoleCardAction}
              roles={roles}
              onOpenRoleDetail={onOpenRoleManagementDetail}
              onGoToChat={onGoToRoleChat}
              onDeleteRole={onRequestDeleteRole}
              onCreateRole={() => onOpenRoleWorkspaceSection("role-create")}
              onImportRoleCard={onImportRoleCard}
            />
          ) : null}
          {mainView.kind === "role-create" ? (
            <RoleCreatePage
              bridgeReady={bridgeReady}
              creating={creating}
              form={newRoleForm}
              onBackToList={onBackToRoleList}
              onCreateRole={onCreateNewRole}
              onResetForm={onResetNewRoleForm}
              onUpdateForm={onUpdateNewRoleForm}
              roleCardImport={roleCardImport}
              onPreviewRoleCard={onPreviewRoleCard}
              onCancelRoleCardImport={onCancelRoleCardImport}
            />
          ) : null}
          {mainView.kind === "role-detail" ? (
            <RoleDetailPage
              activeRole={detailRole}
              activeRoleId={detailRoleId}
              bridgeReady={bridgeReady}
              previewAvatar={previewAvatar}
              currentMood={currentMood}
              moodIllustrationUrl={moodIllustrationUrl}
              roleForm={roleForm}
              roleFormDirty={roleFormDirty}
              savingRole={savingRole}
              onBackToList={onBackToRoleList}
              onGoToChat={() => onGoToRoleChat(detailRoleId)}
              onOpenAssetsPage={onOpenAssetsPage}
              onOpenPluginSettings={onOpenPluginSettings}
              onRoleModelChanged={onRoleModelChanged}
              onUpdateRoleForm={onUpdateRoleForm}
              onResetRoleForm={onResetRoleForm}
              onSaveRole={onSaveRole}
            />
          ) : null}
          {mainView.kind === "role-assets" ? (
            <RoleAssetsPage
              activeRole={detailRole}
              bridgeReady={bridgeReady}
              savingSelection={savingRoleAssets}
              roleForm={roleForm}
              selectedAvatarAsset={selectedAvatarAsset}
              selectedChatBackground={selectedChatBackground}
              onBackToDetail={onBackToRoleDetail}
              onPickAssets={onPickRoleAssets}
              onUpdateAssetOrganization={onUpdateRoleAssetOrganization}
              onRemoveAsset={onRemoveRoleAsset}
              onPluginRoleDataChanged={onPluginRoleDataChanged}
              onSelectAvatarAsset={onSelectAvatarAsset}
              onSelectChatBackground={onSelectChatBackground}
              onUpdateRoleForm={onUpdateRoleForm}
              onSaveSelections={onSaveRoleAssets}
            />
          ) : null}
          {mainView.kind === "settings" ? (
            <SettingsPage
              bridgeReady={bridgeReady}
              section={settingsSection}
              isSectionVisible={isSectionVisible}
              isPluginEnabled={isPluginEnabled}
              activeSubsections={activeSettingsSubsections}
              onChangeSubsection={onChangeSettingsSubsection}
            />
          ) : null}
          {mainView.kind === "plugin-page" && activePluginNavPage ? (
            <activePluginNavPage.Component
              pageId={mainView.pageId}
              activeRoleId={activeRoleId}
              onOpenPluginSettings={() => onOpenPluginSettings(activePluginNavPage.pluginId ?? null)}
            />
          ) : null}
        </main>
      </div>
      <RoleSearchDialog
        open={showSearchDialog}
        query={searchQuery}
        searching={searchingSessions}
        results={searchResults}
        onClose={onCloseSearchDialog}
        onSelectResult={onSelectSearchResult}
        onUpdateQuery={onUpdateSearchQuery}
      />
      <ConfirmDialog
        open={Boolean(pendingDeleteRole)}
        title="确认删除角色"
        description={pendingDeleteRole ? `“${pendingDeleteRole.name}” 删除后会移除角色会话与相关素材。` : ""}
        confirmLabel="确认删除"
        busy={deletingRole}
        onClose={onCloseDeleteDialog}
        onConfirm={onConfirmDeleteRole}
      />
      <ConfirmDialog
        open={leaveConfirmOpen}
        title="放弃未保存的修改？"
        description={`对“${leaveRoleName || "角色"}”的修改还没有保存，离开后会丢失。`}
        confirmLabel="放弃修改"
        cancelLabel="继续编辑"
        onClose={onCancelLeave}
        onConfirm={onConfirmLeave}
      />
      <ChatImageLightbox
        canAddToAssetLibrary={canAddToAssetLibrary}
        canGoToNext={canGoToNextLightboxImage}
        canGoToPrevious={canGoToPreviousLightboxImage}
        canLocateMessage={canLocateLightboxMessage}
        pluginActions={chatImageActions}
        imagePath={chatLatestImagePath}
        addingToAssetLibrary={addingChatImageToAssetLibrary}
        open={chatImageLightboxOpen}
        onAddToAssetLibrary={onAddSelectedChatImageToAssetLibrary}
        onClose={onCloseSelectedChatImageLightbox}
        onGoToNext={onGoToNextChatImage}
        onGoToPrevious={onGoToPreviousChatImage}
        onLocateMessage={onLocateSelectedChatImageMessage}
      />
    </div>
  );
}
