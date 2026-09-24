import type React from "react";
import type { NavPageEntry } from "../plugins/pluginUiRegistry";
import { RoleSidebar } from "../roles/RoleSidebar";
import type { RoleChatPreview } from "../roles/roleChatPreview";
import { RoleWorkspaceSidebar, type RoleWorkspaceSectionId } from "../roles/RoleWorkspaceSidebar";
import { SettingsSidebar, type SettingsSectionId } from "../settings/SettingsSidebar";
import type { AppMainView, RoleRecord } from "../shared/types";

export type SidebarViewState = {
  collapsed: boolean;
  /** Compact window: the sidebar is an overlay drawer over the main pane (see `sidebarLayout.ts`). */
  compact: boolean;
  width: number;
  animating: boolean;
  resizing: boolean;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

type SidebarTrackContentProps = {
  mainView: AppMainView;
  sidebarState: SidebarViewState;
  settingsSection: SettingsSectionId;
  settingsSidebarSections: Array<{ id: SettingsSectionId; label: string }>;
  onOpenSettingsSection: (section: SettingsSectionId) => void;
  roleWorkspaceViewActive: boolean;
  roleWorkspaceSection: RoleWorkspaceSectionId;
  onOpenRoleWorkspaceSection: (section: RoleWorkspaceSectionId) => void;
  /** The role open in role detail / assets (empty on the list and create pages). */
  roleWorkspaceRoleId: string;
  /** A role card mid create / delete, not yet openable. */
  pendingRoleId: string;
  canImportRoleCard: boolean;
  onOpenRoleDetail: (roleId: string) => void;
  onImportRoleCard: () => void;
  roles: RoleRecord[];
  activeRoleId: string;
  unreadCounts: Record<string, number>;
  /** Live chat-list preview of the open conversation (see `previewFromSessionMessages`). */
  activeRolePreview: RoleChatPreview | null;
  bridgeReady: boolean;
  onOpenRole: (roleId: string) => void;
  /** The currently active plugin-page's registry entry, if `mainView.kind === "plugin-page"` and it is still visible. */
  activePluginNavPage: NavPageEntry | undefined;
};

/**
 * Picks and renders whatever occupies the host's resizable `sidebar-track`
 * (see `DesktopAppFrame`): the settings sidebar, the role-workspace
 * sidebar, a plugin-page's own `Sidebar` contribution (issue #226 gap A),
 * or — the long-standing default — the chat role list. Extracted out of
 * `DesktopAppFrame` (already flagged there as "already very large") so this
 * decision has a small, directly mountable seam to test against instead of
 * requiring every one of that component's ~100 other props.
 */
export function SidebarTrackContent({
  mainView,
  sidebarState,
  settingsSection,
  settingsSidebarSections,
  onOpenSettingsSection,
  roleWorkspaceViewActive,
  roleWorkspaceSection,
  onOpenRoleWorkspaceSection,
  roleWorkspaceRoleId,
  pendingRoleId,
  canImportRoleCard,
  onOpenRoleDetail,
  onImportRoleCard,
  roles,
  activeRoleId,
  unreadCounts,
  activeRolePreview,
  bridgeReady,
  onOpenRole,
  activePluginNavPage,
}: SidebarTrackContentProps) {
  const animating = sidebarState.animating && !sidebarState.resizing;

  if (mainView.kind === "settings") {
    return (
      <SettingsSidebar
        sections={settingsSidebarSections}
        activeSection={settingsSection}
        animating={animating}
        collapsed={sidebarState.collapsed}
        width={sidebarState.width}
        onOpenSection={onOpenSettingsSection}
        onBeginResize={sidebarState.onBeginResize}
      />
    );
  }

  if (roleWorkspaceViewActive) {
    return (
      <RoleWorkspaceSidebar
        activeSection={roleWorkspaceSection}
        activeRoleId={roleWorkspaceRoleId}
        roles={roles}
        pendingRoleId={pendingRoleId}
        bridgeReady={bridgeReady}
        canImportRoleCard={canImportRoleCard}
        animating={animating}
        collapsed={sidebarState.collapsed}
        width={sidebarState.width}
        onOpenSection={onOpenRoleWorkspaceSection}
        onOpenRole={onOpenRoleDetail}
        onImportRoleCard={onImportRoleCard}
        onBeginResize={sidebarState.onBeginResize}
      />
    );
  }

  if (mainView.kind === "plugin-page" && activePluginNavPage?.Sidebar) {
    const PluginSidebar = activePluginNavPage.Sidebar;
    return (
      <PluginSidebar
        pageId={mainView.pageId}
        animating={animating}
        collapsed={sidebarState.collapsed}
        width={sidebarState.width}
        onBeginResize={sidebarState.onBeginResize}
      />
    );
  }

  return (
    <RoleSidebar
      roles={roles}
      activeRoleId={activeRoleId}
      unreadCounts={unreadCounts}
      activeRolePreview={activeRolePreview}
      animating={animating}
      bridgeReady={bridgeReady}
      collapsed={sidebarState.collapsed}
      width={sidebarState.width}
      onOpenRole={onOpenRole}
      onCreateRole={() => onOpenRoleWorkspaceSection("role-create")}
      onBeginResize={sidebarState.onBeginResize}
    />
  );
}
