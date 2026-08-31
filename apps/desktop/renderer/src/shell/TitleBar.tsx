import { ArrowsClockwise, CaretLeft, CaretRight, Minus, X } from "@phosphor-icons/react";
import type { WindowControlAction } from "../../../src/bridge/shared";
import { cx } from "../shared/styles";

const titlebarIconClass =
  "[-webkit-app-region:no-drag] m-0 grid h-[calc(var(--titlebar-height)_+_1px)] w-6 place-items-center rounded-md border-0 bg-transparent p-0 text-[#5f6b76] transition-colors hover:bg-black/5 hover:text-[#2c3440] disabled:text-[#b8b8b8] disabled:hover:bg-transparent disabled:hover:text-[#b8b8b8]";
const titlebarSidebarIconClass =
  "relative h-[11px] w-3 rounded-[4px] border-[1.2px] border-current before:absolute before:w-px before:rounded-full before:bg-current before:content-['']";
const windowControlClass =
  "[-webkit-app-region:no-drag] m-0 grid h-[calc(var(--titlebar-height)_+_1px)] w-[46px] place-items-center border-0 bg-transparent p-0 text-[#5f6b76] transition-colors hover:bg-black/5 hover:text-[#2c3440]";

/** Renders the frameless desktop title bar and window controls. */
export function TitleBar({
  sidebarCollapsed,
  windowMaximized,
  canGoBack,
  canGoForward,
  canRefreshSession,
  onToggleSidebar,
  onGoBack,
  onGoForward,
  onRefreshSession,
}: {
  sidebarCollapsed: boolean;
  windowMaximized: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  canRefreshSession: boolean;
  onToggleSidebar: () => void;
  onGoBack: () => void;
  onGoForward: () => void;
  onRefreshSession: () => void;
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
          aria-label="侧边栏"
          aria-expanded={!sidebarCollapsed}
          onClick={onToggleSidebar}
        >
          <span
            className={cx(
              titlebarSidebarIconClass,
              sidebarCollapsed
                ? "before:bottom-[2.2px] before:left-[0.8px] before:top-[2.2px]"
                : "before:bottom-0 before:left-[3.3px] before:top-0",
            )}
            aria-hidden="true"
          />
        </button>
        <button className={cx("titlebar-icon titlebar-back", titlebarIconClass)} type="button" aria-label="后退" onClick={onGoBack} disabled={!canGoBack}>
          <CaretLeft className="h-[17px] w-[17px]" weight="bold" aria-hidden="true" />
        </button>
        <button className={cx("titlebar-icon titlebar-forward", titlebarIconClass)} type="button" aria-label="前进" onClick={onGoForward} disabled={!canGoForward}>
          <CaretRight className="h-[17px] w-[17px]" weight="bold" aria-hidden="true" />
        </button>
        <button className={cx("titlebar-icon titlebar-refresh", titlebarIconClass)} type="button" aria-label="刷新会话" onClick={onRefreshSession} disabled={!canRefreshSession}>
          <ArrowsClockwise className="h-[14px] w-[14px]" aria-hidden="true" />
        </button>
      </div>
      <div className="window-controls ml-auto flex h-full items-center">
        <button className={cx("window-control", windowControlClass)} type="button" aria-label="最小化" onClick={() => controlWindow("minimize")}>
          <Minus className="h-3 w-3" aria-hidden="true" />
        </button>
        <button className={cx("window-control", windowControlClass)} type="button" aria-label="最大化" onClick={() => controlWindow("toggleMaximize")}>
          <span
            className={cx(
              "window-maximize relative block h-[11px] w-[11px] border-current",
              windowMaximized
                ? "before:absolute before:bottom-0 before:left-0 before:h-[8px] before:w-[8px] before:rounded-[1.5px] before:border-[1.3px] before:border-current before:content-[''] after:absolute after:right-0 after:top-0 after:h-[8px] after:w-[8px] after:rounded-[1.5px] after:border-[1.3px] after:border-current after:content-['']"
                : "block rounded-[1.5px] border-[1.3px]",
            )}
          />
        </button>
        <button className={cx("window-control window-control-close", windowControlClass, "hover:bg-[#c42b1c] hover:text-white")} type="button" aria-label="关闭" onClick={() => controlWindow("close")}>
          <X className="h-[13px] w-[13px]" aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
