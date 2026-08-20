import { autoUpdater } from "electron-updater";

/** Starts the packaged-only GitHub Releases update check without blocking desktop startup. */
export function checkForDesktopUpdates(
  packaged: boolean,
  onError: (error: unknown) => void,
): void {
  if (!packaged) {
    return;
  }
  autoUpdater.autoDownload = true;
  autoUpdater.on("error", onError);
  void autoUpdater.checkForUpdatesAndNotify().catch(onError);
}
