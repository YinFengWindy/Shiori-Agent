import type React from "react";
import { cx, secondarySidebarSurfaceClass } from "../shared/styles";

export type PromptTagWorkspaceSectionId = "list" | "create" | "detail";

type PromptTagWorkspaceSidebarProps = {
  activeSection: PromptTagWorkspaceSectionId;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onBackToChat: () => void;
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders prompt-tag workspace navigation using the role-workspace layout. */
export function PromptTagWorkspaceSidebar({ activeSection, collapsed, animating, width, onBackToChat, onOpenSection, onBeginResize }: PromptTagWorkspaceSidebarProps) {
  const actionClass = "flex min-h-[38px] items-center justify-between rounded-xl border border-transparent px-3 text-left text-sm text-[#32363C] transition-colors hover:border-[#D9E0E8] hover:bg-white/70 focus-visible:outline-none";
  const activeClass = "border-[#D9E0E8] bg-white/80 font-medium shadow-[0_1px_2px_rgba(15,23,42,0.05)]";
  return <aside className={cx("relative grid h-full min-h-0 min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] py-3", secondarySidebarSurfaceClass, animating && "transition-[opacity,transform] duration-[480ms]", collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100")} aria-hidden={collapsed} style={{ width }}>
    <button className="mb-3 flex h-8 items-center gap-2 rounded-md border border-transparent px-2 text-left text-sm text-[#6E737A] transition-colors hover:border-[#D9E0E8] hover:bg-white/70" type="button" onClick={onBackToChat}><span className="text-base leading-none">←</span><span>返回应用</span></button>
    <div className="mb-3 grid gap-1 px-2"><button className={cx(actionClass, activeSection === "list" && activeClass)} type="button" onClick={() => onOpenSection("list")}>素材列表</button><button className={cx(actionClass, activeSection === "create" && activeClass)} type="button" onClick={() => onOpenSection("create")}>新建素材</button></div>
    <div className={cx("absolute bottom-0 right-0 top-0 cursor-col-resize bg-transparent", collapsed ? "w-0" : "w-2")} role="separator" aria-label="调整侧边栏宽度" aria-orientation="vertical" onPointerDown={onBeginResize} />
  </aside>;
}
