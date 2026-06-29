import type React from "react";
import { cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

export type RoleWorkspaceSectionId = "roles-list" | "role-create" | "role-detail";

type RoleWorkspaceSidebarProps = {
  activeRoleId: string;
  activeSection: RoleWorkspaceSectionId;
  collapsed: boolean;
  animating: boolean;
  roles: RoleRecord[];
  width: number;
  onBackToChat: () => void;
  onOpenSection: (section: RoleWorkspaceSectionId) => void;
  onOpenRoleDetail: (roleId: string) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders the dedicated role workspace sidebar, matching the settings layout pattern. */
export function RoleWorkspaceSidebar({
  activeRoleId,
  activeSection,
  collapsed,
  animating,
  roles,
  width,
  onBackToChat,
  onOpenSection,
  onOpenRoleDetail,
  onBeginResize,
}: RoleWorkspaceSidebarProps) {
  const activeRole = roles.find((role) => role.id === activeRoleId) ?? null;

  return (
    <aside
      className={cx(
        "role-workspace-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] border-r border-[#E6E8ED] bg-[#EEF1F5] py-3",
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <button
        data-testid="role-workspace-back-button"
        className="mb-3 flex h-8 items-center gap-2 rounded-md border-0 bg-transparent px-2 text-left text-sm text-[#6E737A] hover:bg-white/50"
        type="button"
        onClick={onBackToChat}
      >
        <span className="text-base leading-none">←</span>
        <span>返回应用</span>
      </button>
      <div className="mb-3 grid gap-1 px-2">
        <button
          className={cx(
            "flex min-h-[38px] items-center justify-between rounded-xl border-0 px-3 text-left text-sm text-[#32363C] hover:bg-white/45",
            activeSection === "roles-list" && "bg-[#E4E8ED] font-medium",
          )}
          type="button"
          onClick={() => onOpenSection("roles-list")}
        >
          <span>角色列表</span>
        </button>
        <button
          className={cx(
            "flex min-h-[38px] items-center justify-between rounded-xl border-0 px-3 text-left text-sm text-[#32363C] hover:bg-white/45",
            activeSection === "role-create" && "bg-[#E4E8ED] font-medium",
          )}
          type="button"
          onClick={() => onOpenSection("role-create")}
        >
          <span>新建角色</span>
        </button>
      </div>
      <nav className="scrollbar-soft grid min-h-0 content-start gap-4 overflow-y-auto pr-0">
        <div className="grid gap-1 px-2">
          {roles.map((role) => {
            const isActive = role.id === activeRoleId;
            const sectionActive = activeSection === "role-detail" && isActive;
            return (
              <button
                key={role.id}
                data-testid={`role-workspace-entry-${role.id}`}
                className={cx(
                  "flex min-h-[44px] items-center justify-between rounded-xl border-0 px-3 text-left hover:bg-white/45",
                  sectionActive && "bg-[#E4E8ED]",
                )}
                type="button"
                onClick={() => onOpenRoleDetail(role.id)}
              >
                <div className="min-w-0">
                  <div className={cx("truncate text-sm text-[#32363C]", sectionActive && "font-medium")}>{role.name}</div>
                  <div className="truncate text-[12px] text-[#7A7F86]">{role.description || "未填写角色简介"}</div>
                </div>
              </button>
            );
          })}
        </div>
      </nav>
      <div className="mt-3 border-t border-[#DFE3E8] px-2 pt-3 text-[12px] leading-5 text-[#7A7F86]">
        <div>当前角色</div>
        <div className="mt-1 break-all text-[#5E646B]">{activeRole?.name || "未选择"}</div>
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
      >
        <span className="pointer-events-none absolute bottom-0 right-px top-0 w-px bg-black/5" aria-hidden="true" />
      </div>
    </aside>
  );
}
