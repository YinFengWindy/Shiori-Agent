import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { win32 } from "node:path";
import type { App, Shell } from "electron";
import { installedNotificationAppId, type WindowsNotificationIdentity } from "./windowsIdentity.js";

/** Writes per-user notification metadata without touching Electron's asynchronous COM registration. */
export function writeWindowsNotificationMetadata(identity: WindowsNotificationIdentity) {
  const key = `HKCU\\Software\\Classes\\AppUserModelId\\${identity.appId}`;
  for (const [name, value] of [["DisplayName", identity.name], ["IconUri", identity.iconPath]]) {
    execFileSync("reg.exe", ["add", key, "/v", name!, "/t", "REG_SZ", "/d", value!, "/f"], {
      windowsHide: true,
      stdio: "pipe",
    });
  }
}

/** Repairs only the historical Electron shortcut that incorrectly claimed Shiori's installed identity. */
export function repairLegacyNotificationShortcut(
  shortcutPath: string,
  shortcuts: Pick<Shell, "readShortcutLink" | "writeShortcutLink">,
) {
  if (!existsSync(shortcutPath)) return;
  const details = shortcuts.readShortcutLink(shortcutPath);
  if (details.appUserModelId !== installedNotificationAppId
    || win32.basename(details.target).toLowerCase() !== "electron.exe") return;
  // Preserve its target/arguments and every unrelated shortcut. Changing only its identity releases Shiori.
  if (!shortcuts.writeShortcutLink(shortcutPath, "update", {
    ...details,
    appUserModelId: `${installedNotificationAppId}.dev.legacy`,
  })) throw new Error("Could not repair the legacy Shiori notification shortcut");
}

/** Installs a complete launch command and a recognizable identity before any Windows toast is shown. */
export function registerWindowsNotifications(options: {
  identity: WindowsNotificationIdentity;
  programsPath: string;
  app: Pick<App, "setAsDefaultProtocolClient">;
  shortcuts: Pick<Shell, "readShortcutLink" | "writeShortcutLink">;
  writeMetadata?: typeof writeWindowsNotificationMetadata;
}) {
  const { identity } = options;
  repairLegacyNotificationShortcut(win32.join(options.programsPath, "Electron.lnk"), options.shortcuts);
  (options.writeMetadata ?? writeWindowsNotificationMetadata)(identity);
  if (!options.app.setAsDefaultProtocolClient(identity.protocol, identity.executablePath, identity.arguments)) {
    throw new Error("Could not register Shiori notification activation");
  }
}
