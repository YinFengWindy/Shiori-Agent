import { Menu, Tray } from "electron";
import { desktopWindowIcon } from "./paths.js";

type CreateDesktopTrayOptions = {
  onShowWindow: () => void;
  onQuitRequested: () => void;
  getDesktopPetState?: () => { visible: boolean; available: boolean };
  onToggleDesktopPet?: () => Promise<void>;
};

/** Creates the Windows tray entry used to restore or quit the desktop shell. */
export function createDesktopTray({ onShowWindow, onQuitRequested, getDesktopPetState, onToggleDesktopPet }: CreateDesktopTrayOptions): Tray {
  const tray = new Tray(desktopWindowIcon);
  const refresh = () => {
    const state = getDesktopPetState?.() ?? { visible: false, available: false };
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: "显示主窗口", click: () => onShowWindow() },
        {
          label: state.visible ? "隐藏桌宠" : "显示桌宠",
          enabled: state.available,
          click: () => {
            void onToggleDesktopPet?.().finally(refresh);
          },
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
