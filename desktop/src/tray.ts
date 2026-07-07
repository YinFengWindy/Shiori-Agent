import { Menu, Tray } from "electron";
import { desktopWindowIcon } from "./paths.js";

type CreateDesktopTrayOptions = {
  onShowWindow: () => void;
  onQuitRequested: () => void;
};

/** Creates the Windows tray entry used to restore or quit the desktop shell. */
export function createDesktopTray({ onShowWindow, onQuitRequested }: CreateDesktopTrayOptions): Tray {
  const tray = new Tray(desktopWindowIcon);
  tray.setToolTip("Shiori");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      {
        label: "显示主窗口",
        click: () => onShowWindow(),
      },
      {
        label: "退出 Shiori",
        click: () => onQuitRequested(),
      },
    ]),
  );
  tray.on("click", () => onShowWindow());
  return tray;
}
