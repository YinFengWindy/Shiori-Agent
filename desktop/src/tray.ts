import { Menu, Tray } from "electron";
import { desktopWindowIcon } from "./paths.js";

type CreateDesktopTrayOptions = {
  onShowWindow: () => void;
  onQuitRequested: () => void;
  getDesktopPetState?: () => { enabled: boolean; available: boolean };
  onToggleDesktopPet?: () => void;
};

/** Creates the Windows tray entry used to restore or quit the desktop shell. */
export function createDesktopTray({ onShowWindow, onQuitRequested, getDesktopPetState, onToggleDesktopPet }: CreateDesktopTrayOptions): Tray {
  const tray = new Tray(desktopWindowIcon);
  const refresh = () => {
    const state = getDesktopPetState?.() ?? { enabled: false, available: false };
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: "显示主窗口", click: () => onShowWindow() },
        {
          label: state.enabled ? "桌宠模式：已开启" : "桌宠模式：已关闭",
          enabled: state.available,
          click: () => onToggleDesktopPet?.(),
        },
        { label: "退出 Shiori", click: () => onQuitRequested() },
      ]),
    );
  };
  tray.setToolTip("Shiori");
  refresh();
  tray.on("click", () => onShowWindow());
  tray.on("right-click", refresh);
  return tray;
}
