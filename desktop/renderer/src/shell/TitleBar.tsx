import type { WindowControlAction } from "../../../src/shared";

const menuItems = ["文件", "编辑", "视图", "帮助"] as const;

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
    <header className="titlebar">
      <div className="titlebar-left">
        <button
          className="titlebar-icon titlebar-sidebar"
          type="button"
          aria-label="Sidebar"
          aria-expanded={!sidebarCollapsed}
          onClick={onToggleSidebar}
        >
          <span />
        </button>
        <button className="titlebar-icon titlebar-back" type="button" aria-label="Back" disabled>
          <span />
        </button>
        <button className="titlebar-icon titlebar-forward" type="button" aria-label="Forward" disabled>
          <span />
        </button>
        <nav className="titlebar-menu" aria-label="Application menu">
          {menuItems.map((item) => (
            <button key={item} className="titlebar-menu-item" type="button">
              {item}
            </button>
          ))}
        </nav>
      </div>
      <div className="window-controls">
        <button className="window-control" type="button" aria-label="Minimize" onClick={() => controlWindow("minimize")}>
          <span className="window-minimize" />
        </button>
        <button className="window-control" type="button" aria-label="Maximize" onClick={() => controlWindow("toggleMaximize")}>
          <span className="window-maximize" />
        </button>
        <button className="window-control window-control-close" type="button" aria-label="Close" onClick={() => controlWindow("close")}>
          <span className="window-close" />
        </button>
      </div>
    </header>
  );
}
