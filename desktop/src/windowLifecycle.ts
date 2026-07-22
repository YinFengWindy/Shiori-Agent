import type { BrowserWindow } from "electron";

type DesktopWindowClosePolicy = {
  isQuitting: boolean;
  trayLifecycleEnabled: boolean;
  desktopPetRunning: boolean;
};

/** Keeps the main shell alive while the tray or desktop pet still owns the app lifecycle. */
export function shouldHideDesktopWindowOnClose({
  isQuitting,
  trayLifecycleEnabled,
  desktopPetRunning,
}: DesktopWindowClosePolicy): boolean {
  return !isQuitting && (trayLifecycleEnabled || desktopPetRunning);
}

/** Keeps the desktop renderer alive when the user closes into the tray. */
export function attachDesktopWindowLifecycle(
  window: BrowserWindow,
  { shouldHideOnClose }: { shouldHideOnClose: () => boolean },
): void {
  window.on("close", (event: { preventDefault(): void }) => {
    if (!shouldHideOnClose()) {
      return;
    }
    event.preventDefault();
    window.hide();
  });
}
