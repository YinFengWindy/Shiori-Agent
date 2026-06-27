import type React from "react";
import { toFileUrl } from "../shared/format";
import { bodyTextClass, cardClass, cx, inputClass, primaryButtonClass, textareaClass } from "../shared/styles";
import type { NewRoleFormState, RoleRecord } from "../shared/types";

type RoleSidebarProps = {
  roles: RoleRecord[];
  activeRoleId: string;
  bridgeReady: boolean;
  collapsed: boolean;
  creating: boolean;
  showNewRoleComposer: boolean;
  newRoleForm: NewRoleFormState;
  onOpenSearch: () => void;
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
  collapsed,
  creating,
  showNewRoleComposer,
  newRoleForm,
  onOpenSearch,
  onToggleRoleEditor,
  onUpdateNewRoleForm,
  onCreateRole,
  onOpenRole,
  onBeginResize,
}: RoleSidebarProps) {
  const sidebarEntryClass =
    "sidebar-entry grid min-h-[42px] grid-cols-[24px_1fr] items-center gap-3 rounded-[10px] border-0 bg-transparent px-2 py-0 text-left text-sm text-[#3f3f3f] hover:bg-white/40 focus-visible:bg-white/40 disabled:cursor-default disabled:opacity-[0.45]";
  const roleCardClass =
    "role-card grid min-h-11 grid-cols-[32px_1fr] items-center gap-2.5 rounded-[10px] border-0 bg-transparent px-2 py-1.5 text-left text-[#404040] hover:bg-white/40 focus-visible:bg-white/40 disabled:cursor-default disabled:opacity-60";
  const roleAvatarClass =
    "role-avatar grid h-8 w-8 place-items-center rounded-full border border-[rgba(76,48,24,0.12)] object-cover";

  return (
    <aside className={cx("role-pane relative grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-[18px] overflow-hidden bg-transparent py-[18px] pl-5 pr-[18px]", collapsed && "hidden")}>
      <div className="sidebar-top grid gap-1">
        <button className={sidebarEntryClass} type="button" onClick={onOpenSearch}>
          <span className="sidebar-entry-icon sidebar-entry-search relative block h-5 w-5 text-[#3f3f3f]" aria-hidden="true">
            <span className="absolute left-0.5 top-0.5 h-[11px] w-[11px] rounded-full border-[1.6px] border-current" />
            <span className="absolute bottom-[3px] right-0.5 h-[1.6px] w-2 origin-center rotate-45 rounded-full bg-current" />
          </span>
          <span>搜索</span>
        </button>
        <button className={sidebarEntryClass} type="button" onClick={onToggleRoleEditor} disabled={!activeRoleId}>
          <span className="sidebar-entry-icon sidebar-entry-role grid h-5 w-5 grid-cols-2 gap-1 p-[3px] text-[#3f3f3f]" aria-hidden="true">
            <span className="rounded-full border-[1.5px] border-current" />
            <span className="rounded-full border-[1.5px] border-current" />
            <span className="rounded-full border-[1.5px] border-current" />
            <span className="rounded-full border-[1.5px] border-current" />
          </span>
          <span>角色</span>
        </button>
        {showNewRoleComposer ? (
          <div className="create-form mt-3 grid gap-2.5">
            <input
              data-testid="new-role-name"
              className={inputClass}
              value={newRoleForm.name}
              onChange={(event) => onUpdateNewRoleForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="New role name"
            />
            <input
              data-testid="new-role-description"
              className={inputClass}
              value={newRoleForm.description}
              onChange={(event) => onUpdateNewRoleForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Short description"
            />
            <textarea
              data-testid="new-role-prompt"
              className={cx("compact-prompt", textareaClass, "min-h-24")}
              value={newRoleForm.systemPrompt}
              onChange={(event) => onUpdateNewRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
              placeholder="Role system prompt"
            />
            <button data-testid="create-role-button" className={cx("primary-btn text-sm", primaryButtonClass)} type="button" onClick={onCreateRole} disabled={creating || !bridgeReady}>
              {creating ? "Creating..." : "Create Role"}
            </button>
          </div>
        ) : null}
      </div>
      <div className={cx("role-list scrollbar-soft scrollbar-soft-accent grid min-h-0 content-start gap-1.5 overflow-x-hidden overflow-y-auto pr-0.5", bodyTextClass)} data-testid="role-list">
        {roles.length ? roles.map((role) => (
          <button
            key={role.id}
            data-testid={`role-card-${role.id}`}
            className={cx(roleCardClass, role.id === activeRoleId && "active bg-white/50")}
            type="button"
            disabled={!bridgeReady}
            onClick={() => onOpenRole(role.id)}
          >
            {role.avatar_abs ? (
              <img
                className={roleAvatarClass}
                src={toFileUrl(role.avatar_abs)}
                alt={`${role.name} avatar`}
              />
            ) : (
              <span className={cx(roleAvatarClass, "role-avatar-fallback bg-white/55 text-sm font-bold text-accent-deep")}>{role.name.slice(0, 1).toUpperCase()}</span>
            )}
            <span className="role-name min-w-0 truncate font-semibold">{role.name}</span>
          </button>
        )) : (
          <div className={cx("empty-card", cardClass, "p-4")}>No roles yet.</div>
        )}
      </div>
      <div
        className="sidebar-resize-handle absolute bottom-0 right-0 top-0 w-2 cursor-col-resize bg-transparent hover:bg-black/5 focus-visible:bg-black/5"
        role="separator"
        aria-label="Resize sidebar"
        aria-orientation="vertical"
        onPointerDown={onBeginResize}
      />
    </aside>
  );
}
