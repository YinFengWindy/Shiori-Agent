import { app, ipcMain, Notification, shell, type BrowserWindow } from "electron";
import { join } from "node:path";
import { logDesktopDiagnostic } from "../diagnostics.js";
import { desktopNotificationIcon } from "../paths.js";
import { DesktopMessageNotifications } from "./controller.js";
import type { NotificationActivation } from "./activation.js";
import { notificationChannels } from "./contract.js";
import type { WindowsNotificationIdentity } from "./windowsIdentity.js";
import { registerWindowsNotifications } from "./windowsRegistration.js";
import { windowsNotificationToast } from "./windowsToast.js";

/** Wires native notifications and private main-window click delivery to Electron. */
export function createDesktopMessageNotifications(options: {
  getWindow(): BrowserWindow | null;
  activation: NotificationActivation;
  windowsIdentity: WindowsNotificationIdentity | null;
}) {
  const { navigation } = options.activation;
  const active = new Set<Notification>();
  const reportError = (error: unknown) => logDesktopDiagnostic({
    scope: "main", event: "notification.failed", payload: { error },
  });
  let registrationReady = true;
  if (options.windowsIdentity) {
    try {
      registerWindowsNotifications({
        identity: options.windowsIdentity,
        programsPath: join(app.getPath("appData"), "Microsoft", "Windows", "Start Menu", "Programs"),
        app,
        shortcuts: shell,
      });
    } catch (error) {
      // A broken OS registration disables notifications without interrupting bridge or chat delivery.
      registrationReady = false;
      reportError(error);
    }
  }
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
    isSupported: () => registrationReady && Notification.isSupported(),
    show: ({ title, body, roleId }, onClick) => {
      const notification = new Notification({
        title, body, icon: desktopNotificationIcon,
        ...options.windowsIdentity ? {
          toastXml: windowsNotificationToast({
            protocol: options.windowsIdentity.protocol, roleId, title, body, iconPath: desktopNotificationIcon,
          }),
        } : {},
      });
      active.add(notification);
      // Windows launches the explicit protocol, including when the native Notification object is gone.
      if (!options.windowsIdentity) notification.on("click", onClick);
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
    openChat: (roleId) => options.activation.openChat(roleId),
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
