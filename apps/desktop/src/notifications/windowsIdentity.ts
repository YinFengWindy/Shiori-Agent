import { createHash } from "node:crypto";
import { win32 } from "node:path";

/** The installed identity also used by electron-builder and existing Start Menu shortcuts. */
export const installedNotificationAppId = "com.yinfengwindy.shiori";

/** Builds separate OS identities and complete activation commands for installed and development apps. */
export function windowsNotificationIdentity(options: {
  packaged: boolean;
  appPath: string;
  userDataPath: string;
  executablePath: string;
  iconPath: string;
}) {
  const suffix = createHash("sha256")
    .update(`${win32.resolve(options.appPath).toLowerCase()}\n${win32.resolve(options.userDataPath).toLowerCase()}`)
    .digest("hex").slice(0, 16);
  const appId = options.packaged ? installedNotificationAppId : `${installedNotificationAppId}.dev.${suffix}`;
  return {
    appId,
    protocol: options.packaged ? "shiori-notification" : `shiori-notification-dev-${suffix}`,
    name: options.packaged ? "Shiori" : "Shiori (Development)",
    executablePath: options.executablePath,
    iconPath: options.iconPath,
    arguments: [
      ...options.packaged ? [] : [options.appPath],
      `--shiori-user-data-dir=${options.userDataPath}`,
    ],
  };
}

/** Shared registration data; all executable paths come from the running app, never a toast URI. */
export type WindowsNotificationIdentity = ReturnType<typeof windowsNotificationIdentity>;
