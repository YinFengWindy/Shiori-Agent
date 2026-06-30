import type React from "react";
import { cx } from "../shared/styles";

export type RoleWorkspaceSectionId = "roles-list" | "role-create" | "role-detail" | "role-assets";

type RoleWorkspaceSidebarProps = {
  activeSection: RoleWorkspaceSectionId;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onBackToChat: () => void;
  onOpenSection: (section: RoleWorkspaceSectionId) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders the dedicated role workspace sidebar, matching the settings layout pattern. */
export function RoleWorkspaceSidebar({
  activeSection,
  collapsed,
  animating,
  width,
  onBackToChat,
  onOpenSection,
  onBeginResize,
}: RoleWorkspaceSidebarProps) {
  const sidebarActionClass =
    "flex min-h-[38px] items-center justify-between rounded-xl border border-transparent px-3 text-left text-sm text-[#32363C] transition-colors hover:border-[#D9E0E8] hover:bg-white/70 focus-visible:border-[#D9E0E8] focus-visible:bg-white/70 focus-visible:outline-none";
  const sidebarBackClass =
    "mb-3 flex h-8 items-center gap-2 rounded-md border border-transparent bg-transparent px-2 text-left text-sm text-[#6E737A] transition-colors hover:border-[#D9E0E8] hover:bg-white/70 focus-visible:border-[#D9E0E8] focus-visible:bg-white/70 focus-visible:outline-none";

  return (
    <aside
      className={cx(
        "role-workspace-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] bg-[#EEF1F5] py-3",
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <button
        data-testid="role-workspace-back-button"
        className={sidebarBackClass}
        type="button"
        onClick={onBackToChat}
      >
        <span className="text-base leading-none">←</span>
        <span>返回应用</span>
      </button>
      <div className="mb-3 grid gap-1 px-2">
        <button
          className={cx(
            sidebarActionClass,
            activeSection === "roles-list" && "border-[#D9E0E8] bg-white/80 font-medium shadow-[0_1px_2px_rgba(15,23,42,0.05)]",
          )}
          type="button"
          onClick={() => onOpenSection("roles-list")}
        >
          <span>角色列表</span>
        </button>
        <button
          className={cx(
            sidebarActionClass,
            activeSection === "role-create" && "border-[#D9E0E8] bg-white/80 font-medium shadow-[0_1px_2px_rgba(15,23,42,0.05)]",
          )}
          type="button"
          onClick={() => onOpenSection("role-create")}
        >
          <span>新建角色</span>
        </button>
        {(activeSection === "role-detail" || activeSection === "role-assets") ? (
          <button
            className={cx(
              sidebarActionClass,
              activeSection === "role-assets" && "border-[#D9E0E8] bg-white/80 font-medium shadow-[0_1px_2px_rgba(15,23,42,0.05)]",
            )}
            type="button"
            onClick={() => onOpenSection("role-assets")}
          >
            <span>素材库</span>
          </button>
        ) : null}
      </div>
      <div className="min-h-0" />
      <div className="mt-3 border-t border-[#DFE3E8] px-2 pt-3 text-[12px] leading-5 text-[#7A7F86]">
        <div>角色工作区</div>
        <div className="mt-1 break-all text-[#5E646B]">
          {activeSection === "role-create"
            ? "当前正在新建角色"
            : activeSection === "role-assets"
              ? "在这里上传并选择当前角色的头像与顶栏立绘"
              : "在这里管理角色列表与角色详情"}
        </div>
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
