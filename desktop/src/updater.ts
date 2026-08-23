import * as electronUpdater from "electron-updater";

/** Starts the packaged-only GitHub Releases update check without blocking desktop startup. */
export function checkForDesktopUpdates(
  packaged: boolean,
  onError: (error: unknown) => void,
): void {
  if (!packaged) {
    return;
  }
  electronUpdater.autoUpdater.autoDownload = true;
  electronUpdater.autoUpdater.on("error", onError);
  void electronUpdater.autoUpdater.checkForUpdatesAndNotify().catch(onError);
}
