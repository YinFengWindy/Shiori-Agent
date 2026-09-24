import type React from "react";
import { Plus } from "@phosphor-icons/react";
import { SidebarResizeHandle } from "../shared/SidebarResizeHandle";
import { cx, pressableClass, sidebarContentMotionClass, sidebarNavItemClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import { PetalIcon } from "../shared/ui/icons";
import { RoleAvatar } from "./RoleAvatar";

type RoleSidebarProps = {
  roles: RoleRecord[];
  activeRoleId: string;
  unreadCounts: Record<string, number>;
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenRole: (roleId: string) => void;
  onCreateRole: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Friendly placeholder for a chat list with no roles yet, with the one action that fixes it. */
function RoleSidebarEmptyState({ onCreateRole }: { onCreateRole: () => void }) {
  return (
    <div className="grid justify-items-center gap-3 px-2 pt-10 text-center" data-testid="role-list-empty">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent">
        <PetalIcon className="h-5 w-5" />
      </span>
      <span className="text-body-sm text-ink-muted">还没有角色</span>
      <button
        className={cx(
          pressableClass,
          "inline-flex h-8 items-center gap-1.5 rounded-md border border-white/70 bg-gradient-accent px-3 text-body-sm text-ink shadow-soft hover:brightness-[1.03]",
        )}
        type="button"
        onClick={onCreateRole}
      >
        <Plus className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        新建角色
      </button>
    </div>
  );
}

/** Renders the conversation list sidebar and the sidebar resize handle. */
export function RoleSidebar({
  roles,
  activeRoleId,
  unreadCounts,
  bridgeReady,
  collapsed,
  animating,
  width,
  onOpenRole,
  onCreateRole,
  onBeginResize,
}: RoleSidebarProps) {
  const roleCardClass = cx(
    sidebarNavItemClass,
    "grid min-h-[42px] grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-2.5 px-2 text-left text-[13px] leading-none text-ink-secondary disabled:cursor-default disabled:opacity-60",
  );

  return (
    <aside
      className={cx(
        "role-pane relative grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] overflow-hidden bg-transparent py-[18px]",
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[18px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <div className="role-list scrollbar-soft scrollbar-soft-accent grid min-h-0 content-start gap-1.5 overflow-x-hidden overflow-y-auto pr-0" data-testid="role-list">
        {roles.length ? roles.map((role) => (
          <button
            key={role.id}
            data-testid={`role-card-${role.id}`}
            className={cx(roleCardClass, role.id === activeRoleId && "active bg-white text-ink shadow-soft")}
            type="button"
            disabled={!bridgeReady}
            onClick={() => onOpenRole(role.id)}
          >
            <RoleAvatar role={role} />
            <span className="role-name min-w-0 truncate font-semibold leading-none">{role.name}</span>
            <span className="grid min-h-5 min-w-5 place-items-center">
              {unreadCounts[role.id] ? (
                <span
                  className="h-2.5 w-2.5 rounded-full bg-danger"
                  aria-label={`${role.name} 有未读主动消息`}
                  title={`${role.name} 有未读主动消息`}
                />
              ) : null}
            </span>
          </button>
        )) : bridgeReady ? (
          <RoleSidebarEmptyState onCreateRole={onCreateRole} />
        ) : null}
      </div>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
