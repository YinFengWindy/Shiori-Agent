import type React from "react";
import { cx, secondarySidebarSurfaceClass, sidebarNavItemClass } from "../shared/styles";

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
    "flex min-h-[38px] items-center justify-between px-3 text-left text-sm text-[#3a4453]",
  );
  const activeSectionClass =
    "bg-white/90 font-medium text-[#3a4453] shadow-[0_1px_2px_rgba(15,23,42,0.05)] hover:bg-white focus-visible:bg-white";

  return (
    <aside
      className={cx(
        "role-workspace-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] py-3",
        secondarySidebarSurfaceClass,
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
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
