import type React from "react";
import { cx, secondarySidebarSurfaceClass, sidebarNavItemClass } from "../shared/styles";

export type PromptTagWorkspaceSectionId = "list" | "create" | "detail";

type PromptTagWorkspaceSidebarProps = {
  activeSection: PromptTagWorkspaceSectionId;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders prompt-tag workspace navigation using the role-workspace layout. */
export function PromptTagWorkspaceSidebar({ activeSection, collapsed, animating, width, onOpenSection, onBeginResize }: PromptTagWorkspaceSidebarProps) {
  const actionClass = cx(
    sidebarNavItemClass,
    "flex min-h-[38px] items-center justify-between px-3 text-left text-sm text-[#3a4453]",
  );
  const activeClass =
    "bg-white/90 font-medium text-[#3a4453] shadow-[0_1px_2px_rgba(15,23,42,0.05)] hover:bg-white focus-visible:bg-white";
  return <aside className={cx("relative grid h-full min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] py-3", secondarySidebarSurfaceClass, animating && "transition-[opacity,transform] duration-[480ms]", collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100")} aria-hidden={collapsed} style={{ width }}>
    <div className="grid gap-1 px-2"><button className={cx(actionClass, activeSection === "list" && activeClass)} type="button" onClick={() => onOpenSection("list")}>提示词列表</button><button className={cx(actionClass, activeSection === "create" && activeClass)} type="button" onClick={() => onOpenSection("create")}>新建提示词</button></div>
    <div className={cx("absolute bottom-0 right-0 top-0 cursor-col-resize bg-transparent", collapsed ? "w-0" : "w-2")} role="separator" aria-label="调整侧边栏宽度" aria-orientation="vertical" onPointerDown={onBeginResize} />
  </aside>;
}
