import { useEffect, useRef, useState } from "react";
import { ArrowsClockwise, CaretLeft, CaretRight, Minus, SidebarSimple, X } from "@phosphor-icons/react";
import type { WindowControlAction } from "../../../src/bridge/shared";
import { cx } from "../shared/styles";

const menuItems = ["文件", "编辑", "视图", "帮助"] as const;
type MenuItem = {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
};
const titlebarIconClass =
  "[-webkit-app-region:no-drag] m-0 grid h-[calc(var(--titlebar-height)_+_1px)] w-6 place-items-center rounded-md border-0 bg-transparent p-0 text-[#5f6b76] transition-colors hover:bg-black/5 hover:text-[#2c3440] disabled:text-[#b8b8b8] disabled:hover:bg-transparent disabled:hover:text-[#b8b8b8]";
const windowControlClass =
  "[-webkit-app-region:no-drag] m-0 grid h-[calc(var(--titlebar-height)_+_1px)] w-[46px] place-items-center border-0 bg-transparent p-0 text-[#5f6b76] transition-colors hover:bg-black/5 hover:text-[#2c3440]";

/** Renders the frameless desktop title bar and window controls. */
export function TitleBar({
  sidebarCollapsed,
  windowMaximized,
  canGoBack,
  canGoForward,
  canRefreshSession,
  canEditRole,
  onToggleSidebar,
  onGoBack,
  onGoForward,
  onRefreshSession,
  onCreateRole,
  onEditRole,
  onOpenSettings,
  onRefreshBridge,
  onRestartBridge,
}: {
  sidebarCollapsed: boolean;
  windowMaximized: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  canRefreshSession: boolean;
  canEditRole: boolean;
  onToggleSidebar: () => void;
  onGoBack: () => void;
  onGoForward: () => void;
  onRefreshSession: () => void;
  onCreateRole: () => void;
  onEditRole: () => void;
  onOpenSettings: () => void;
  onRefreshBridge: () => void;
  onRestartBridge: () => void;
}) {
  const [openMenu, setOpenMenu] = useState<typeof menuItems[number] | null>(null);
  const rootRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent): void {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpenMenu(null);
      }
    }

    function handleEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setOpenMenu(null);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, []);

  function controlWindow(action: WindowControlAction) {
    void window.miraDesktop.windowControl(action);
  }

  function toggleMenu(menu: typeof menuItems[number]): void {
    setOpenMenu((current) => (current === menu ? null : menu));
  }

  function selectMenuItem(action: () => void): void {
    setOpenMenu(null);
    action();
  }

  const menuActions: Record<typeof menuItems[number], MenuItem[]> = {
    文件: [
      { label: "新对话", onSelect: onCreateRole },
    ],
    编辑: [
      { label: "编辑当前角色", onSelect: onEditRole, disabled: !canEditRole },
    ],
    视图: [
      { label: sidebarCollapsed ? "展开侧边栏" : "收起侧边栏", onSelect: onToggleSidebar },
      { label: "设置", onSelect: onOpenSettings },
    ],
    帮助: [
      { label: "刷新连接桥", onSelect: onRefreshBridge },
      { label: "重启连接桥", onSelect: onRestartBridge },
    ],
  };

  return (
    <header ref={rootRef} className="titlebar [-webkit-app-region:drag] flex h-[calc(var(--titlebar-height)+5px)] select-none items-center justify-between bg-transparent text-[#747474]">
      <div className="titlebar-left flex h-full items-center gap-0 pl-0.5">
        <button
          className={cx("titlebar-icon titlebar-sidebar", titlebarIconClass)}
          type="button"
          aria-label="侧边栏"
          aria-expanded={!sidebarCollapsed}
          onClick={onToggleSidebar}
        >
          <SidebarSimple className="h-[15px] w-[15px]" weight={sidebarCollapsed ? "regular" : "fill"} aria-hidden="true" />
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
        <nav className="titlebar-menu ml-0.5 flex h-full items-center gap-0" aria-label="应用菜单">
          {menuItems.map((item) => (
            <div key={item} className="titlebar-menu-entry relative">
              <button
                className={cx(
                  "titlebar-menu-item [-webkit-app-region:no-drag] m-0 h-6 min-w-11 rounded-md border-0 bg-transparent px-2 text-[13px] tracking-normal text-[#5f6b76] transition-colors hover:bg-black/5 hover:text-[#2c3440]",
                  openMenu === item && "bg-black/5 text-[#2c3440]",
                )}
                type="button"
                aria-haspopup="menu"
                aria-expanded={openMenu === item}
                onClick={() => toggleMenu(item)}
              >
                {item}
              </button>
              {openMenu === item ? (
                <div className="titlebar-dropdown [-webkit-app-region:no-drag] absolute left-0 top-[calc(100%+4px)] z-20 min-w-max rounded-md border border-stroke bg-white px-1.5 py-1.5 shadow-[0_12px_32px_rgba(15,23,42,0.12)]">
                  {menuActions[item].map((menuAction) => (
                    <button
                      key={menuAction.label}
                      className="flex h-8 w-full items-center justify-start rounded-md border-0 bg-transparent px-2.5 text-left text-[13px] leading-none text-[#3a4453] transition-colors hover:bg-[#F3F6FA] hover:text-[#182230] disabled:cursor-default disabled:text-[#b8b8b8] disabled:hover:bg-transparent disabled:hover:text-[#b8b8b8]"
                      type="button"
                      disabled={menuAction.disabled}
                      onClick={() => selectMenuItem(menuAction.onSelect)}
                    >
                      {menuAction.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </nav>
      </div>
      <div className="window-controls ml-auto flex h-full items-center">
        <button className={cx("window-control", windowControlClass)} type="button" aria-label="最小化" onClick={() => controlWindow("minimize")}>
          <Minus className="h-3 w-3" aria-hidden="true" />
        </button>
        <button className={cx("window-control", windowControlClass)} type="button" aria-label="最大化" onClick={() => controlWindow("toggleMaximize")}>
          <span
            className={cx(
              "window-maximize relative block h-[10px] w-[10px] border-current",
              windowMaximized
                ? "rounded-[1.5px] border-[1.3px] before:absolute before:-bottom-[2.5px] before:-right-[2.5px] before:h-[9px] before:w-[9px] before:rounded-[2px] before:border-[1.3px] before:border-current before:bg-white before:content-['']"
                : "rounded-[1.5px] border-[1.3px]",
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
