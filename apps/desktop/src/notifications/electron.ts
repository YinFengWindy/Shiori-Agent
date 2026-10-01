import { ipcMain, Notification, type BrowserWindow } from "electron";
import { logDesktopDiagnostic } from "../diagnostics.js";
import { DesktopMessageNotifications } from "./controller.js";
import { NotificationNavigation } from "./navigation.js";
import { notificationChannels } from "./contract.js";

/** Wires native notifications and private main-window click delivery to Electron. */
export function createDesktopMessageNotifications(options: {
  getWindow(): BrowserWindow | null;
  showWindow(): BrowserWindow;
}) {
  const navigation = new NotificationNavigation();
  const active = new Set<Notification>();
  const reportError = (error: unknown) => logDesktopDiagnostic({
    scope: "main", event: "notification.failed", payload: { error },
  });
  ipcMain.handle(notificationChannels.pending, (event) => (
    event.sender === options.getWindow()?.webContents ? navigation.getPending() : null
  ));
  ipcMain.handle(notificationChannels.acknowledge, (event, id: unknown) => {
    if (event.sender === options.getWindow()?.webContents && typeof id === "number") {
      navigation.acknowledge(id);
    }
  });
  const controller = new DesktopMessageNotifications({
    isForeground: () => {
      const window = options.getWindow();
      return Boolean(window && !window.isDestroyed() && window.isVisible()
        && !window.isMinimized() && window.isFocused());
    },
    isSupported: () => Notification.isSupported(),
    show: ({ title, body }, onClick) => {
      const notification = new Notification({ title, body });
      active.add(notification);
      notification.on("click", onClick);
      notification.on("close", () => active.delete(notification));
      notification.on("failed", (_event, error) => {
        active.delete(notification);
        reportError(error);
      });
      try {
        notification.show();
      } catch (error) {
        active.delete(notification);
        throw error;
      }
    },
    openChat: (roleId) => {
      navigation.select(roleId);
      const window = options.showWindow();
      window.webContents.send(notificationChannels.clicked);
    },
    onError: reportError,
  });
  return {
    handleEvent: (event: Parameters<typeof controller.handleEvent>[0]) => controller.handleEvent(event),
    dispose: () => {
      for (const notification of active) notification.close();
      active.clear();
      ipcMain.removeHandler(notificationChannels.pending);
      ipcMain.removeHandler(notificationChannels.acknowledge);
    },
  };
}
