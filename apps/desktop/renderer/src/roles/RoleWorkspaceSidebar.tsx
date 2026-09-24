import type React from "react";
import { Plus, SquaresFour, UploadSimple } from "@phosphor-icons/react";
import { SidebarResizeHandle } from "../shared/SidebarResizeHandle";
import { cx, pressableClass, secondarySidebarSurfaceClass, sidebarContentMotionClass, sidebarNavItemClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import { RoleAvatar } from "./RoleAvatar";

export type RoleWorkspaceSectionId = "roles-list" | "role-create" | "role-detail" | "role-assets";

type RoleWorkspaceSidebarProps = {
  activeSection: RoleWorkspaceSectionId;
  /** The role shown in detail / assets, highlighted in the list; empty elsewhere. */
  activeRoleId: string;
  roles: RoleRecord[];
  /** A role card still being created or deleted; its row cannot be opened yet. */
  pendingRoleId: string;
  bridgeReady: boolean;
  /** Whether a role card import can start (bridge up, no import already running). */
  canImportRoleCard: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenSection: (section: RoleWorkspaceSectionId) => void;
  onOpenRole: (roleId: string) => void;
  onImportRoleCard: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

const actionButtonClass = cx(
  pressableClass,
  "inline-flex h-8 min-w-0 items-center justify-center gap-1.5 rounded-md border px-2.5 text-body-sm disabled:cursor-default disabled:opacity-50",
);

/**
 * The role workspace's secondary sidebar: create / import actions on top,
 * then every role, so moving between roles never needs a trip back to the
 * card grid. 「全部角色」 returns to that grid, which stays the landing page
 * when no role is selected.
 */
export function RoleWorkspaceSidebar({
  activeSection,
  activeRoleId,
  roles,
  pendingRoleId,
  bridgeReady,
  canImportRoleCard,
  collapsed,
  animating,
  width,
  onOpenSection,
  onOpenRole,
  onImportRoleCard,
  onBeginResize,
}: RoleWorkspaceSidebarProps) {
  const rowClass = cx(
    sidebarNavItemClass,
    "grid w-full min-w-0 items-center gap-2.5 px-2 text-left text-ink-secondary disabled:cursor-default disabled:opacity-60",
  );
  const activeRowClass = "bg-white text-ink shadow-soft hover:bg-white focus-visible:bg-white";
  const creating = activeSection === "role-create";

  return (
    <aside
      className={cx(
        "role-workspace-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_auto_minmax(0,1fr)] gap-2 py-3",
        secondarySidebarSurfaceClass,
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      aria-label="角色"
      style={{ width }}
    >
      <div className="flex min-w-0 gap-1.5 px-2">
        <button
          className={cx(
            actionButtonClass,
            "shrink-0 border-white/70 bg-gradient-accent text-ink shadow-soft hover:brightness-[1.03]",
            creating && "ring-2 ring-accent-soft",
          )}
          type="button"
          aria-current={creating ? "page" : undefined}
          onClick={() => onOpenSection("role-create")}
        >
          <Plus className="h-3.5 w-3.5 shrink-0" weight="bold" aria-hidden="true" />
          新建
        </button>
        <button
          className={cx(actionButtonClass, "flex-1 border-line bg-surface text-ink-secondary hover:border-line-accent hover:bg-accent-softer hover:text-accent-text")}
          type="button"
          data-testid="sidebar-import-role-card"
          disabled={!canImportRoleCard}
          onClick={onImportRoleCard}
        >
          <UploadSimple className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">导入角色卡</span>
        </button>
      </div>
      <div className="px-2">
        <button
          className={cx(rowClass, "min-h-9 grid-cols-[20px_minmax(0,1fr)_auto] text-body-sm", activeSection === "roles-list" && activeRowClass)}
          type="button"
          aria-current={activeSection === "roles-list" ? "page" : undefined}
          onClick={() => onOpenSection("roles-list")}
        >
          <SquaresFour className="h-4 w-4 justify-self-center text-ink-muted" aria-hidden="true" />
          <span className="truncate font-medium">全部角色</span>
          <span className="text-caption tabular-nums text-ink-muted">{roles.length}</span>
        </button>
      </div>
      <div className="role-workspace-role-list scrollbar-soft scrollbar-soft-accent grid min-h-0 content-start gap-1 overflow-y-auto overflow-x-hidden px-2 pb-1" data-testid="role-workspace-role-list">
        {roles.map((role) => {
          const active = role.id === activeRoleId && (activeSection === "role-detail" || activeSection === "role-assets");
          return (
            <button
              key={role.id}
              className={cx(rowClass, "min-h-[48px] grid-cols-[32px_minmax(0,1fr)] py-1.5", active && activeRowClass)}
              type="button"
              data-testid={`role-workspace-role-${role.id}`}
              aria-current={active ? "page" : undefined}
              disabled={!bridgeReady || role.id === pendingRoleId}
              onClick={() => onOpenRole(role.id)}
            >
              <RoleAvatar role={role} />
              <span className="grid min-w-0 gap-0.5">
                <span className="truncate text-body-sm font-semibold leading-5 text-ink">{role.name}</span>
                <span className="truncate text-caption leading-4 text-ink-muted">{role.description || "未填写角色简介"}</span>
              </span>
            </button>
          );
        })}
      </div>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
