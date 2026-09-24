import type React from "react";
import { SidebarResizeHandle } from "../shared/SidebarResizeHandle";
import { cx, secondarySidebarSurfaceClass, sidebarContentMotionClass, sidebarNavItemClass } from "../shared/styles";

export type RoleWorkspaceSectionId = "roles-list" | "role-create" | "role-detail" | "role-assets";

type RoleWorkspaceSidebarProps = {
  activeSection: RoleWorkspaceSectionId;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenSection: (section: RoleWorkspaceSectionId) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders the dedicated role workspace sidebar, matching the settings layout pattern. */
export function RoleWorkspaceSidebar({
  activeSection,
  collapsed,
  animating,
  width,
  onOpenSection,
  onBeginResize,
}: RoleWorkspaceSidebarProps) {
  const sidebarActionClass = cx(
    sidebarNavItemClass,
    "flex min-h-[38px] items-center justify-between px-3 text-left text-sm text-ink-secondary",
  );
  const activeSectionClass =
    "bg-white/90 font-medium text-ink shadow-soft hover:bg-white focus-visible:bg-white";

  return (
    <aside
      className={cx(
        "role-workspace-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] py-3",
        secondarySidebarSurfaceClass,
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <div className="grid gap-1 px-2">
        <button
          className={cx(sidebarActionClass, activeSection === "roles-list" && activeSectionClass)}
          type="button"
          onClick={() => onOpenSection("roles-list")}
        >
          <span>角色列表</span>
        </button>
        <button
          className={cx(sidebarActionClass, activeSection === "role-create" && activeSectionClass)}
          type="button"
          onClick={() => onOpenSection("role-create")}
        >
          <span>新建角色</span>
        </button>
      </div>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
