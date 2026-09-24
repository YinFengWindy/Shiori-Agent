import type React from "react";
import { SidebarResizeHandle } from "../../../apps/desktop/renderer/src/shared/SidebarResizeHandle";
import { cx, secondarySidebarSurfaceClass, sidebarContentMotionClass, sidebarNavItemClass } from "../../../apps/desktop/renderer/src/shared/styles";

export type PromptTagWorkspaceSectionId = "list" | "create" | "detail";

type PromptTagWorkspaceSidebarProps = {
  activeSection: PromptTagWorkspaceSectionId;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void;
  onBackToStudio: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/**
 * Renders prompt-tag workspace navigation into the host's resizable sidebar
 * track (issue #226 gap A) — same resize contract as `ImageStudioSidebar`.
 * `onBackToStudio` (added in #180, once this workspace became part of the
 * single novelai nav.page instead of its own top-level view) is kept.
 */
export function PromptTagWorkspaceSidebar({
  activeSection,
  collapsed,
  animating,
  width,
  onOpenSection,
  onBackToStudio,
  onBeginResize,
}: PromptTagWorkspaceSidebarProps) {
  const actionClass = cx(
    sidebarNavItemClass,
    "flex min-h-[38px] items-center justify-between px-3 text-left text-sm text-ink-secondary",
  );
  const activeClass =
    "bg-white/90 font-medium text-ink shadow-soft hover:bg-white focus-visible:bg-white";
  return (
    <aside
      className={cx(
        "relative grid h-full min-h-0 min-w-0 content-start gap-1 py-3",
        secondarySidebarSurfaceClass,
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <div className="grid gap-1 px-2">
        <button className={actionClass} type="button" onClick={onBackToStudio}>返回生图</button>
        <button className={cx(actionClass, activeSection === "list" && activeClass)} type="button" onClick={() => onOpenSection("list")}>提示词列表</button>
        <button className={cx(actionClass, activeSection === "create" && activeClass)} type="button" onClick={() => onOpenSection("create")}>新建提示词</button>
      </div>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
