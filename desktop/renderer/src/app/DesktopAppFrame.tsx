import type React from "react";
import { ChatImageLightbox } from "../chat/ChatImageLightbox";
import { ChatSurface } from "../chat/ChatSurface";
import { ImageStudioPage } from "../image/ImageStudioPage";
import { ImageStudioSidebar } from "../image/ImageStudioSidebar";
import { useImageStudioState } from "../image/useImageStudioState";
import { ConfirmDialog } from "../roles/ConfirmDialog";
import { RoleAssetsPage } from "../roles/RoleAssetsPage";
import { RoleCreatePage } from "../roles/RoleCreatePage";
import { RoleDetailPage } from "../roles/RoleDetailPage";
import { RoleManagementPage } from "../roles/RoleManagementPage";
import { RoleSearchDialog } from "../roles/RoleSearchDialog";
import { RoleSidebar } from "../roles/RoleSidebar";
import { RoleWorkspaceSidebar, type RoleWorkspaceSectionId } from "../roles/RoleWorkspaceSidebar";
import { SettingsPage } from "../settings/SettingsPage";
import { SettingsSidebar, type SettingsSectionId } from "../settings/SettingsSidebar";
import { cx } from "../shared/styles";
import type {
  AppMainView,
  ChatReplyTarget,
  NewRoleFormState,
  PendingRoleCardAction,
  RoleFormState,
  RoleRecord,
  RoleSearchResult,
  SessionPayload,
} from "../shared/types";
import { TitleBar } from "../shell/TitleBar";
import type { WorkspaceFeedback } from "./appState";

type ImageStudioStateViewModel = ReturnType<typeof useImageStudioState>;

type SidebarViewState = {
  collapsed: boolean;
  width: number;
  animating: boolean;
  resizing: boolean;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

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
  canEditRole: boolean;
  onToggleSidebar: () => void;
  onGoBack: () => void;
  onGoForward: () => void;
  onRefreshSession: () => void;
  onCreateRole: () => void;
  onEditRole: () => void;
  onOpenSettings: () => void;
  onRefreshBridge: () => void;
  onRestartBridge: () => void;
  shellResizing: boolean;
  sidebarState: SidebarViewState;
  mainView: AppMainView;
  settingsSection: SettingsSectionId;
  settingsDirty: boolean;
  settingsSearch: string;
  onSettingsSearchChange: (value: string) => void;
  onBackToChat: () => void;
  onOpenSettingsSection: (section: SettingsSectionId) => void;
  imageStudioViewActive: boolean;
  roleWorkspaceViewActive: boolean;
  roleWorkspaceSection: RoleWorkspaceSectionId;
  onOpenRoleWorkspaceSection: (section: RoleWorkspaceSectionId) => void;
  roles: RoleRecord[];
  activeRoleId: string;
  unreadCounts: Record<string, number>;
  bridgeReady: boolean;
  onOpenSearch: () => void;
  onOpenRolesWorkspace: () => void;
  onOpenRole: (roleId: string) => void;
  onOpenImageStudio: () => void;
  imageStudioState: ImageStudioStateViewModel;
  workspaceFeedback: WorkspaceFeedback | null;
  activeRole: RoleRecord | null;
  activeSession: SessionPayload | null;
  chatLatestImagePath: string;
  chatLatestImagePosition: number;
  chatLatestImageSidebar: RightSidebarViewState;
  chatLatestImageSidebarCount: number;
  currentMood: string;
  moodIllustrationBindingHit: boolean;
  moodIllustrationUrl: string;
  hasMoodIllustrationBinding: boolean;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  draft: string;
  headerTitle: string;
  highlightedMessageKey: string;
  notice: string;
  pendingChatAttachments: string[];
  chatReplyTarget: ChatReplyTarget | null;
  isVisibleChatSending: boolean;
  visibleIllustrationUrl: string;
  onGoToNextChatImage: () => void;
  onGoToPreviousChatImage: () => void;
  onOpenChatImageLightbox: () => void;
  onOpenChatImagePreview: (target: { historyKey: string }) => void;
  onPickChatAttachments: () => void;
  onOpenRoleDetail: () => void;
  onJumpToMessage: (messageKey: string) => void;
  onClearChatReplyTarget: () => void;
  onBeginAttachmentDrag: (path: string) => void;
  onCopyMessage: (content: string) => void;
  onQuoteMessage: (target: ChatReplyTarget) => void;
  onRemovePendingChatAttachment: (path: string) => void;
  onSendMessage: (contentOverride?: string) => void;
  onUpdateDraft: (value: string) => void;
  imageHistorySidebar: RightSidebarViewState;
  detailRole: RoleRecord | null;
  pendingRoleCardAction: PendingRoleCardAction;
  onOpenRoleManagementDetail: (roleId: string) => void;
  onRequestDeleteRole: (roleId: string) => void;
  creating: boolean;
  newRoleForm: NewRoleFormState;
  onBackToRoleList: () => void;
  onCreateNewRole: () => void;
  onResetNewRoleForm: () => void;
  onUpdateNewRoleForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
  detailRoleId: string;
  activeIllustration: string;
  previewAvatar: string | null;
  chatBackgroundUrl: string;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onOpenAssetsPage: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
  savingRoleAssets: boolean;
  selectedAvatarAsset: string;
  selectedChatBackground: string;
  onBackToRoleDetail: () => void;
  onPickRoleAssets: () => void;
  onRemoveRoleAsset: (path: string) => void;
  onSelectAvatarAsset: (path: string) => void;
  onSelectChatBackground: (path: string) => void;
  onSaveRoleAssets: (nextSelection?: { avatarAsset?: string; chatBackground?: string; moodIllustrationBindings?: Record<string, string>; moodCatalog?: string[] }) => void;
  onSettingsMetaChange: (meta: { configPath: string; dirty: boolean }) => void;
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
  addingChatImageToAssetLibrary: boolean;
  chatImageLightboxOpen: boolean;
  onAddSelectedChatImageToAssetLibrary: () => void;
  onCloseSelectedChatImageLightbox: () => void;
  onLocateSelectedChatImageMessage: () => void;
};

/** Renders the desktop shell around the already-prepared application state. */
export function DesktopAppFrame({
  sidebarCollapsed,
  windowMaximized,
  canGoBack,
  canGoForward,
  canRefreshSession,
  canEditRole,
  onToggleSidebar,
  onGoBack,
  onGoForward,
  onRefreshSession,
  onCreateRole,
  onEditRole,
  onOpenSettings,
  onRefreshBridge,
  onRestartBridge,
  shellResizing,
  sidebarState,
  mainView,
  settingsSection,
  settingsDirty,
  settingsSearch,
  onSettingsSearchChange,
  onBackToChat,
  onOpenSettingsSection,
  imageStudioViewActive,
  roleWorkspaceViewActive,
  roleWorkspaceSection,
  onOpenRoleWorkspaceSection,
  roles,
  activeRoleId,
  unreadCounts,
  bridgeReady,
  onOpenSearch,
  onOpenRolesWorkspace,
  onOpenRole,
  onOpenImageStudio,
  imageStudioState,
  workspaceFeedback,
  activeRole,
  activeSession,
  chatLatestImagePath,
  chatLatestImagePosition,
  chatLatestImageSidebar,
  chatLatestImageSidebarCount,
  currentMood,
  moodIllustrationBindingHit,
  moodIllustrationUrl,
  hasMoodIllustrationBinding,
  conversationEndRef,
  draft,
  headerTitle,
  highlightedMessageKey,
  notice,
  pendingChatAttachments,
  chatReplyTarget,
  isVisibleChatSending,
  visibleIllustrationUrl,
  onGoToNextChatImage,
  onGoToPreviousChatImage,
  onOpenChatImageLightbox,
  onOpenChatImagePreview,
  onPickChatAttachments,
  onOpenRoleDetail,
  onJumpToMessage,
  onClearChatReplyTarget,
  onBeginAttachmentDrag,
  onCopyMessage,
  onQuoteMessage,
  onRemovePendingChatAttachment,
  onSendMessage,
  onUpdateDraft,
  imageHistorySidebar,
  detailRole,
  pendingRoleCardAction,
  onOpenRoleManagementDetail,
  onRequestDeleteRole,
  creating,
  newRoleForm,
  onBackToRoleList,
  onCreateNewRole,
  onResetNewRoleForm,
  onUpdateNewRoleForm,
  detailRoleId,
  activeIllustration,
  previewAvatar,
  chatBackgroundUrl,
  roleForm,
  roleFormDirty,
  savingRole,
  onOpenAssetsPage,
  onUpdateRoleForm,
  onResetRoleForm,
  onSaveRole,
  savingRoleAssets,
  selectedAvatarAsset,
  selectedChatBackground,
  onBackToRoleDetail,
  onPickRoleAssets,
  onRemoveRoleAsset,
  onSelectAvatarAsset,
  onSelectChatBackground,
  onSaveRoleAssets,
  onSettingsMetaChange,
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
  addingChatImageToAssetLibrary,
  chatImageLightboxOpen,
  onAddSelectedChatImageToAssetLibrary,
  onCloseSelectedChatImageLightbox,
  onLocateSelectedChatImageMessage,
}: DesktopAppFrameProps) {
  return (
    <div className="app-frame grid h-screen grid-rows-app overflow-hidden bg-[var(--app-bg)]">
      <TitleBar
        sidebarCollapsed={sidebarCollapsed}
        windowMaximized={windowMaximized}
        canGoBack={canGoBack}
        canGoForward={canGoForward}
        canRefreshSession={canRefreshSession}
        canEditRole={canEditRole}
        onToggleSidebar={onToggleSidebar}
        onGoBack={onGoBack}
        onGoForward={onGoForward}
        onRefreshSession={onRefreshSession}
        onCreateRole={onCreateRole}
        onEditRole={onEditRole}
        onOpenSettings={onOpenSettings}
        onRefreshBridge={onRefreshBridge}
        onRestartBridge={onRestartBridge}
      />
      <div
        className={cx(
          "desktop-shell grid min-h-0 overflow-hidden bg-transparent",
          shellResizing && "sidebar-resizing cursor-col-resize select-none",
        )}
        style={{
          gridTemplateColumns: "minmax(0, auto) minmax(0, 1fr)",
        }}
      >
        <div
          className={cx(
            "sidebar-track relative min-h-0 overflow-hidden",
            sidebarState.animating && "transition-[width] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          )}
          style={{ width: sidebarState.collapsed ? 0 : sidebarState.width }}
        >
          {mainView.kind === "settings" ? (
            <SettingsSidebar
              activeSection={settingsSection}
              animating={sidebarState.animating && !sidebarState.resizing}
              collapsed={sidebarState.collapsed}
              dirty={settingsDirty}
              width={sidebarState.width}
              onBackToChat={onBackToChat}
              onOpenSection={onOpenSettingsSection}
              onSearchChange={onSettingsSearchChange}
              onBeginResize={sidebarState.onBeginResize}
              search={settingsSearch}
            />
          ) : imageStudioViewActive ? (
            <ImageStudioSidebar
              bridgeReady={bridgeReady}
              animating={sidebarState.animating && !sidebarState.resizing}
              collapsed={sidebarState.collapsed}
              width={sidebarState.width}
              form={imageStudioState.form}
              nsfwEnabled={imageStudioState.nsfwEnabled}
              addQualityTags={imageStudioState.addQualityTags}
              undesiredContentPreset={imageStudioState.undesiredContentPreset}
              roleItems={imageStudioState.roleItems}
              submitting={imageStudioState.submitting}
              validationError={imageStudioState.validationError}
              onBackToChat={onBackToChat}
              onBeginResize={sidebarState.onBeginResize}
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
              animating={sidebarState.animating && !sidebarState.resizing}
              collapsed={sidebarState.collapsed}
              width={sidebarState.width}
              onBackToChat={onBackToChat}
              onOpenSection={onOpenRoleWorkspaceSection}
              onBeginResize={sidebarState.onBeginResize}
            />
          ) : (
            <RoleSidebar
              roles={roles}
              activeRoleId={activeRoleId}
              unreadCounts={unreadCounts}
              animating={sidebarState.animating && !sidebarState.resizing}
              bridgeReady={bridgeReady}
              collapsed={sidebarState.collapsed}
              width={sidebarState.width}
              onOpenSearch={onOpenSearch}
              onOpenRolesWorkspace={onOpenRolesWorkspace}
              onOpenRole={onOpenRole}
              onOpenImageStudio={onOpenImageStudio}
              onOpenSettings={onOpenSettings}
              onBeginResize={sidebarState.onBeginResize}
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
              chatLatestImagePath={chatLatestImagePath}
              chatLatestImagePosition={chatLatestImagePosition}
              chatLatestImageSidebarAnimating={chatLatestImageSidebar.animating && !chatLatestImageSidebar.resizing}
              chatLatestImageSidebarCollapsed={chatLatestImageSidebar.collapsed}
              chatLatestImageSidebarCount={chatLatestImageSidebarCount}
              chatLatestImageSidebarWidth={chatLatestImageSidebar.width}
              currentMood={currentMood}
              moodIllustrationBindingHit={moodIllustrationBindingHit}
              moodIllustrationUrl={moodIllustrationUrl}
              hasMoodIllustrationBinding={hasMoodIllustrationBinding}
              conversationEndRef={conversationEndRef}
              draft={draft}
              headerTitle={headerTitle}
              highlightedMessageKey={highlightedMessageKey}
              notice={notice}
              pendingChatAttachments={pendingChatAttachments}
              chatReplyTarget={chatReplyTarget}
              sending={isVisibleChatSending}
              visibleIllustrationUrl={visibleIllustrationUrl}
              onBeginChatLatestImageSidebarResize={chatLatestImageSidebar.beginResize}
              onGoToNextChatImage={onGoToNextChatImage}
              onGoToPreviousChatImage={onGoToPreviousChatImage}
              onOpenChatImageLightbox={onOpenChatImageLightbox}
              onOpenChatImagePreview={onOpenChatImagePreview}
              onPickChatAttachments={onPickChatAttachments}
              onOpenRoleDetail={onOpenRoleDetail}
              onJumpToMessage={onJumpToMessage}
              onClearChatReplyTarget={onClearChatReplyTarget}
              onBeginAttachmentDrag={onBeginAttachmentDrag}
              onCopyMessage={onCopyMessage}
              onQuoteMessage={onQuoteMessage}
              onRemovePendingChatAttachment={onRemovePendingChatAttachment}
              onSendMessage={onSendMessage}
              onToggleChatLatestImageSidebar={chatLatestImageSidebar.toggle}
              onUpdateDraft={onUpdateDraft}
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
              onOpenRoleDetail={onOpenRoleManagementDetail}
              onDeleteRole={onRequestDeleteRole}
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
              onBackToList={onBackToRoleList}
              onOpenAssetsPage={onOpenAssetsPage}
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
              onRemoveAsset={onRemoveRoleAsset}
              onSelectAvatarAsset={onSelectAvatarAsset}
              onSelectChatBackground={onSelectChatBackground}
              onUpdateRoleForm={onUpdateRoleForm}
              onSaveSelections={onSaveRoleAssets}
            />
          ) : null}
          {mainView.kind === "settings" ? (
            <SettingsPage
              bridgeReady={bridgeReady}
              search={settingsSearch}
              section={settingsSection}
              onMetaChange={onSettingsMetaChange}
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
      <ChatImageLightbox
        canAddToAssetLibrary={canAddToAssetLibrary}
        canGoToNext={canGoToNextLightboxImage}
        canGoToPrevious={canGoToPreviousLightboxImage}
        canLocateMessage={canLocateLightboxMessage}
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
