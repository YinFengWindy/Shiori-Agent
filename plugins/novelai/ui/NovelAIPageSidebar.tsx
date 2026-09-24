import type { ReactNode } from "react";
import { BookBookmark, ImageSquare } from "@phosphor-icons/react";
import type { PluginNavPageSidebarComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { SidebarResizeHandle } from "../../../apps/desktop/renderer/src/shared/SidebarResizeHandle";
import { cx, secondarySidebarSurfaceClass, sidebarContentMotionClass, sidebarNavItemClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { backToStudio, openPromptTagLibrary, useNovelAiPageStore } from "./novelAiPageStore";

const itemClass = cx(
  sidebarNavItemClass,
  "flex min-h-[38px] items-center gap-2.5 px-3 text-left text-sm text-ink-secondary",
);
const activeItemClass = "bg-white/80 font-medium text-ink shadow-soft hover:bg-white focus-visible:bg-white";

function NavItem({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button className={cx(itemClass, active && activeItemClass)} type="button" aria-current={active ? "page" : undefined} onClick={onClick}>
      <span className={cx("flex shrink-0", active ? "text-accent-text" : "text-ink-muted")} aria-hidden="true">{icon}</span>
      <span className="min-w-0 truncate">{label}</span>
    </button>
  );
}

/**
 * The novelai `nav.page` sidebar (issue #226 gap A), rendered by the host
 * into its resizable track: the workspace's two places, 生图 and 提示词库,
 * in the same look as the settings sidebar. The generation form itself lives
 * in the page so it stays visible when a small window folds the sidebar away.
 */
export function NovelAIPageSidebar({ animating, collapsed, width, onBeginResize, onNavigate }: PluginNavPageSidebarComponentProps) {
  const { view } = useNovelAiPageStore();
  // A view switch here is invisible to the host; tell it so a compact overlay drawer closes.
  const go = (open: () => void) => () => {
    open();
    onNavigate?.();
  };
  return (
    <aside
      className={cx(
        "relative grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] py-5",
        secondarySidebarSurfaceClass,
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
      data-testid="novelai-sidebar"
    >
      <nav className="grid min-h-0 content-start gap-1 px-2 pr-0" aria-label="生图工作区">
        <NavItem active={view === "studio"} icon={<ImageSquare className="h-[18px] w-[18px]" />} label="生图" onClick={go(backToStudio)} />
        <NavItem
          active={view === "prompt-tags"}
          icon={<BookBookmark className="h-[18px] w-[18px]" />}
          label="提示词库"
          onClick={go(openPromptTagLibrary)}
        />
      </nav>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
