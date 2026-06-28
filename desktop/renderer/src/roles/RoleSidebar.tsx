import type React from "react";
import { toFileUrl } from "../shared/format";
import { bodyTextClass, cardClass, cx, inputClass, primaryButtonClass, textareaClass } from "../shared/styles";
import type { NewRoleFormState, RoleRecord } from "../shared/types";

type RoleSidebarProps = {
  roles: RoleRecord[];
  activeRoleId: string;
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  creating: boolean;
  showNewRoleComposer: boolean;
  newRoleForm: NewRoleFormState;
  onOpenSearch: () => void;
  onToggleRoleEditor: () => void;
  onUpdateNewRoleForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
  onCreateRole: () => void;
  onOpenRole: (roleId: string) => void;
  onOpenSettings: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders role navigation, new-role creation, and the sidebar resize handle. */
export function RoleSidebar({
  roles,
  activeRoleId,
  bridgeReady,
  collapsed,
  animating,
  width,
  creating,
  showNewRoleComposer,
  newRoleForm,
  onOpenSearch,
  onToggleRoleEditor,
  onUpdateNewRoleForm,
  onCreateRole,
  onOpenRole,
  onOpenSettings,
  onBeginResize,
}: RoleSidebarProps) {
  const sidebarEntryClass =
    "sidebar-entry grid min-h-[38px] grid-cols-[20px_1fr] items-center gap-2.5 rounded-[10px] border border-transparent bg-transparent px-2 py-0 text-left text-[13px] text-[#3f3f3f] transition-colors hover:border-[#D9E0E8] hover:bg-[#E2E8EF] focus-visible:border-[#D9E0E8] focus-visible:bg-[#E2E8EF] disabled:cursor-default disabled:opacity-[0.45]";
  const roleCardClass =
    "role-card grid min-h-[42px] grid-cols-[32px_1fr] items-center gap-2.5 rounded-[10px] border border-transparent bg-transparent px-2 py-0 text-left text-[13px] leading-none text-[#404040] transition-colors hover:border-[#D9E0E8] hover:bg-[#E2E8EF] focus-visible:border-[#D9E0E8] focus-visible:bg-[#E2E8EF] disabled:cursor-default disabled:opacity-60";
  const roleAvatarClass =
    "role-avatar grid h-8 w-8 place-items-center rounded-full border border-[rgba(76,48,24,0.12)] object-cover";
  const footerEntryClass =
    "grid min-h-[42px] grid-cols-[20px_1fr] items-center gap-2.5 rounded-[12px] border border-transparent bg-transparent px-2.5 py-0 text-left text-[13px] leading-none transition-colors hover:border-[#D9E0E8] hover:bg-[#E2E8EF] focus-visible:border-[#D9E0E8] focus-visible:bg-[#E2E8EF]";

  return (
    <aside
      className={cx(
        "role-pane relative grid h-full min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-[18px] overflow-hidden bg-transparent py-[18px]",
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[18px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <div className="sidebar-top grid gap-1">
        <button className={sidebarEntryClass} type="button" onClick={onOpenSearch}>
          <span className="sidebar-entry-icon sidebar-entry-search grid h-5 w-5 place-items-center text-[#2c2c2c]" aria-hidden="true">
            <svg viewBox="0 0 1024 1024" className="h-4 w-4 fill-current">
              <path d="M447.957333 149.333333c164.949333 0 298.666667 133.717333 298.666667 298.666667 0 64.96-20.736 125.056-55.936 173.952l177.365333 177.365333a42.666667 42.666667 0 0 1-60.330666 60.330667l-177.365334-177.365333A297.344 297.344 0 0 1 447.957333 746.666667c-164.949333 0-298.666667-133.717333-298.666666-298.666667S283.008 149.333333 447.957333 149.333333z m0 85.333334C330.154667 234.666667 234.624 330.197333 234.624 448s95.530667 213.333333 213.333333 213.333333 213.333333-95.530667 213.333334-213.333333-95.530667-213.333333-213.333334-213.333333z" />
            </svg>
          </span>
          <span>搜索</span>
        </button>
        <button className={sidebarEntryClass} type="button" onClick={onToggleRoleEditor} disabled={!activeRoleId}>
          <span className="sidebar-entry-icon sidebar-entry-role grid h-5 w-5 place-items-center text-[#2c2c2c]" aria-hidden="true">
            <svg viewBox="0 0 1024 1024" className="h-4 w-4 fill-current">
              <path d="M356.774 578.668C279.812 528.088 229 440.978 229 342c0-156.297 126.703-283 283-283s283 126.703 283 283c0 98.978-50.812 186.088-127.774 236.668C808.213 638.98 907 778.953 907 942c0 24.3-19.7 44-44 44s-44-19.7-44-44c0-169.551-137.449-307-307-307S205 772.449 205 942c0 24.3-19.7 44-44 44s-44-19.7-44-44c0-163.047 98.787-303.02 239.774-363.332zM512 537c107.696 0 195-87.304 195-195s-87.304-195-195-195-195 87.304-195 195 87.304 195 195 195z" />
            </svg>
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
      <div className={cx("role-list scrollbar-soft scrollbar-soft-accent grid min-h-0 content-start gap-1.5 overflow-x-hidden overflow-y-auto pr-0", bodyTextClass)} data-testid="role-list">
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
              <span className={cx(roleAvatarClass, "bg-white/55 text-sm font-bold text-accent-deep")}>{role.name.slice(0, 1).toUpperCase()}</span>
            )}
            <span className="role-name min-w-0 truncate font-semibold leading-none">{role.name}</span>
          </button>
        )) : (
          <div className={cx("empty-card", cardClass, "p-4")}>No roles yet.</div>
        )}
      </div>
      <div className="mt-1 border-t border-[#DFE4EA] pt-2">
        <button
          data-testid="open-settings-button"
          className={footerEntryClass}
          type="button"
          onClick={onOpenSettings}
        >
          <span className="grid h-5 w-5 place-items-center text-[#2c2c2c]" aria-hidden="true">
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3.2" />
              <path d="M19.4 15a1.66 1.66 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06A1.66 1.66 0 0 0 15 19.4a1.66 1.66 0 0 0-1 .6 1.66 1.66 0 0 0-.4 1V21a2 2 0 0 1-4 0v-.09A1.66 1.66 0 0 0 9 20a1.66 1.66 0 0 0-1-.6 1.66 1.66 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.66 1.66 0 0 0 4.6 15a1.66 1.66 0 0 0-.6-1 1.66 1.66 0 0 0-1-.4H3a2 2 0 0 1 0-4h.09A1.66 1.66 0 0 0 4 9a1.66 1.66 0 0 0 .6-1 1.66 1.66 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.66 1.66 0 0 0 9 4.6a1.66 1.66 0 0 0 1-.6 1.66 1.66 0 0 0 .4-1V3a2 2 0 0 1 4 0v.09A1.66 1.66 0 0 0 15 4a1.66 1.66 0 0 0 1 .6 1.66 1.66 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.66 1.66 0 0 0 19.4 9c.19.32.29.69.29 1.06 0 .37-.1.74-.29 1.06-.19.32-.47.58-.8.76-.33.18-.7.27-1.08.27h0" />
            </svg>
          </span>
          <span className="min-w-0 truncate font-medium text-[#242424]">设置</span>
        </button>
      </div>
      <div
        className={cx(
          "sidebar-resize-handle absolute bottom-0 right-0 top-0 cursor-col-resize bg-transparent",
          collapsed ? "w-0" : "w-2",
        )}
        role="separator"
        aria-label="Resize sidebar"
        aria-orientation="vertical"
        onPointerDown={onBeginResize}
      >
        <span className="pointer-events-none absolute bottom-0 right-px top-0 w-px bg-black/5" aria-hidden="true" />
      </div>
    </aside>
  );
}
