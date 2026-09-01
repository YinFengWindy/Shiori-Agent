import type React from "react";
import { toFileUrl } from "../shared/format";
import { cx, sidebarNavItemClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

type RoleSidebarProps = {
  roles: RoleRecord[];
  activeRoleId: string;
  unreadCounts: Record<string, number>;
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenRole: (roleId: string) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

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
  onBeginResize,
}: RoleSidebarProps) {
  const roleCardClass = cx(
    sidebarNavItemClass,
    "grid min-h-[42px] grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-2.5 px-2 text-left text-[13px] leading-none text-[#3a4453] disabled:cursor-default disabled:opacity-60",
  );
  const roleAvatarClass =
    "role-avatar grid h-8 w-8 place-items-center rounded-full border border-[rgba(76,48,24,0.12)] object-cover";

  return (
    <aside
      className={cx(
        "role-pane relative grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] overflow-hidden bg-transparent py-[18px]",
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
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
            className={cx(roleCardClass, role.id === activeRoleId && "active bg-white text-[#2c3440] shadow-[0_6px_18px_rgba(15,23,42,0.08)]")}
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
            <span className="grid min-h-5 min-w-5 place-items-center">
              {unreadCounts[role.id] ? (
                <span
                  className="h-2.5 w-2.5 rounded-full bg-[#DA4B4B]"
                  aria-label={`${role.name} 有未读主动消息`}
                  title={`${role.name} 有未读主动消息`}
                />
              ) : null}
            </span>
          </button>
        )) : (
          null
        )}
      </div>
      <div
        className={cx(
          "sidebar-resize-handle absolute bottom-0 right-0 top-0 cursor-col-resize bg-transparent",
          collapsed ? "w-0" : "w-2",
        )}
        role="separator"
        aria-label="调整侧边栏宽度"
        aria-orientation="vertical"
        onPointerDown={onBeginResize}
      />
    </aside>
  );
}
