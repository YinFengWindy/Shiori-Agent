import type { WindowControlAction } from "../../../src/shared";
import { cx } from "../shared/styles";

const menuItems = ["文件", "编辑", "视图", "帮助"] as const;
const titlebarIconClass =
  "[-webkit-app-region:no-drag] m-0 grid h-[calc(var(--titlebar-height)_+_1px)] w-6 place-items-center rounded-md border-0 bg-transparent p-0 text-inherit disabled:text-[#b8b8b8] enabled:hover:bg-black/5";
const titlebarArrowClass =
  "relative h-2.5 w-[13px] before:absolute before:top-[4.5px] before:h-[1.3px] before:w-[11px] before:rounded-full before:bg-current before:content-[''] after:absolute after:top-[2.5px] after:h-[5px] after:w-[5px] after:border-l-[1.3px] after:border-t-[1.3px] after:border-current after:content-['']";
const windowControlClass =
  "[-webkit-app-region:no-drag] m-0 grid h-[calc(var(--titlebar-height)_+_1px)] w-[46px] place-items-center border-0 bg-transparent p-0 text-inherit hover:bg-black/5";

/** Renders the frameless desktop title bar and window controls. */
export function TitleBar({
  sidebarCollapsed,
  onToggleSidebar,
}: {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
}) {
  function controlWindow(action: WindowControlAction) {
    void window.miraDesktop.windowControl(action);
  }

  return (
    <header className="titlebar [-webkit-app-region:drag] flex h-[calc(var(--titlebar-height)+5px)] select-none items-center justify-between bg-transparent text-[#747474]">
      <div className="titlebar-left flex h-full items-center gap-0 pl-0.5">
        <button
          className={cx("titlebar-icon titlebar-sidebar", titlebarIconClass)}
          type="button"
          aria-label="Sidebar"
          aria-expanded={!sidebarCollapsed}
          onClick={onToggleSidebar}
        >
          <span className="relative h-[11px] w-3 rounded-[4px] border-[1.2px] border-current before:absolute before:bottom-[1.5px] before:left-[2.5px] before:top-[1.5px] before:w-[1.2px] before:rounded-full before:bg-current before:content-['']" />
        </button>
        <button className={cx("titlebar-icon titlebar-back", titlebarIconClass)} type="button" aria-label="Back" disabled>
          <span className={cx(titlebarArrowClass, "before:left-0.5 after:left-[1.5px] after:-rotate-45")} />
        </button>
        <button className={cx("titlebar-icon titlebar-forward", titlebarIconClass)} type="button" aria-label="Forward" disabled>
          <span className={cx(titlebarArrowClass, "before:right-0.5 after:right-[1.5px] after:rotate-[135deg]")} />
        </button>
        <nav className="titlebar-menu ml-0.5 flex h-full items-center gap-0" aria-label="Application menu">
          {menuItems.map((item) => (
            <button
              key={item}
              className="titlebar-menu-item [-webkit-app-region:no-drag] m-0 h-6 min-w-11 cursor-default rounded-md border-0 bg-transparent px-2 text-[13px] tracking-normal text-inherit hover:bg-black/5"
              type="button"
            >
              {item}
            </button>
          ))}
        </nav>
      </div>
      <div className="window-controls ml-auto flex h-full items-center">
        <button className={cx("window-control", windowControlClass)} type="button" aria-label="Minimize" onClick={() => controlWindow("minimize")}>
          <span className="window-minimize relative h-[11px] w-[11px] before:absolute before:inset-x-0 before:top-1.5 before:h-[1.5px] before:bg-current before:content-['']" />
        </button>
        <button className={cx("window-control", windowControlClass)} type="button" aria-label="Maximize" onClick={() => controlWindow("toggleMaximize")}>
          <span className="window-maximize h-[11px] w-[11px] rounded-sm border-[1.5px] border-current" />
        </button>
        <button className={cx("window-control window-control-close", windowControlClass, "hover:bg-[#c42b1c] hover:text-white")} type="button" aria-label="Close" onClick={() => controlWindow("close")}>
          <span className="window-close relative h-[11px] w-[11px] before:absolute before:left-[5px] before:top-[-1px] before:h-[15px] before:w-[1.5px] before:rotate-45 before:bg-current before:content-[''] after:absolute after:left-[5px] after:top-[-1px] after:h-[15px] after:w-[1.5px] after:-rotate-45 after:bg-current after:content-['']" />
        </button>
      </div>
    </header>
  );
}
