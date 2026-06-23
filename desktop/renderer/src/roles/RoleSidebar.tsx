import type React from "react";
import { toFileUrl } from "../shared/format";
import type { NewRoleFormState, RoleRecord } from "../shared/types";

type RoleSidebarProps = {
  roles: RoleRecord[];
  activeRoleId: string;
  bridgeReady: boolean;
  creating: boolean;
  showNewRoleComposer: boolean;
  newRoleForm: NewRoleFormState;
  onToggleNewRoleComposer: () => void;
  onToggleRoleEditor: () => void;
  onUpdateNewRoleForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
  onCreateRole: () => void;
  onOpenRole: (roleId: string) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders role navigation, new-role creation, and the sidebar resize handle. */
export function RoleSidebar({
  roles,
  activeRoleId,
  bridgeReady,
  creating,
  showNewRoleComposer,
  newRoleForm,
  onToggleNewRoleComposer,
  onToggleRoleEditor,
  onUpdateNewRoleForm,
  onCreateRole,
  onOpenRole,
  onBeginResize,
}: RoleSidebarProps) {
  return (
    <aside className="role-pane">
      <div className="sidebar-top">
        <button className="sidebar-entry" type="button" onClick={onToggleNewRoleComposer}>
          <span className="sidebar-entry-icon sidebar-entry-new" aria-hidden="true" />
          <span>新对话</span>
        </button>
        <button className="sidebar-entry" type="button">
          <span className="sidebar-entry-icon sidebar-entry-search" aria-hidden="true" />
          <span>搜索</span>
        </button>
        <button className="sidebar-entry" type="button" onClick={onToggleRoleEditor} disabled={!activeRoleId}>
          <span className="sidebar-entry-icon sidebar-entry-role" aria-hidden="true" />
          <span>角色</span>
        </button>
        {showNewRoleComposer ? (
          <div className="create-form">
            <input
              data-testid="new-role-name"
              value={newRoleForm.name}
              onChange={(event) => onUpdateNewRoleForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="New role name"
            />
            <input
              data-testid="new-role-description"
              value={newRoleForm.description}
              onChange={(event) => onUpdateNewRoleForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Short description"
            />
            <textarea
              data-testid="new-role-prompt"
              className="compact-prompt"
              value={newRoleForm.systemPrompt}
              onChange={(event) => onUpdateNewRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
              placeholder="Role system prompt"
            />
            <button data-testid="create-role-button" className="primary-btn" type="button" onClick={onCreateRole} disabled={creating || !bridgeReady}>
              {creating ? "Creating..." : "Create Role"}
            </button>
          </div>
        ) : null}
      </div>
      <div className="role-list" data-testid="role-list">
        {roles.length ? roles.map((role) => (
          <button
            key={role.id}
            data-testid={`role-card-${role.id}`}
            className={`role-card${role.id === activeRoleId ? " active" : ""}`}
            type="button"
            disabled={!bridgeReady}
            onClick={() => onOpenRole(role.id)}
          >
            {role.avatar_abs ? (
              <img
                className="role-avatar"
                src={toFileUrl(role.avatar_abs)}
                alt={`${role.name} avatar`}
              />
            ) : (
              <span className="role-avatar role-avatar-fallback">{role.name.slice(0, 1).toUpperCase()}</span>
            )}
            <span className="role-name">{role.name}</span>
          </button>
        )) : (
          <div className="empty-card">No roles yet.</div>
        )}
      </div>
      <div
        className="sidebar-resize-handle"
        role="separator"
        aria-label="Resize sidebar"
        aria-orientation="vertical"
        onPointerDown={onBeginResize}
      />
    </aside>
  );
}
