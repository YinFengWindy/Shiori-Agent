import type { BrowserWindow } from "electron";

/** Windows message emitted when a draggable non-client region is double-clicked. */
export const windowsNonClientLeftButtonDoubleClick = 0x00a3;

type DesktopPetNativeInteractionOptions = {
  window: BrowserWindow;
  platform?: NodeJS.Platform;
  onOpenPetRole: () => void;
  onShowContextMenu: (window: BrowserWindow) => void;
};

/** Preserves desktop-pet commands that renderer pointer events cannot receive inside a native drag region. */
export function attachDesktopPetNativeInteractions({
  window,
  platform = process.platform,
  onOpenPetRole,
  onShowContextMenu,
}: DesktopPetNativeInteractionOptions): void {
  window.webContents.on("before-mouse-event", (_event, input) => {
    const mouseInput = input as { type?: unknown; button?: unknown; clickCount?: unknown };
    if (mouseInput.type === "mouseDown" && mouseInput.button === "left" && mouseInput.clickCount === 2) {
      onOpenPetRole();
    }
  });
  window.on("system-context-menu", (event) => {
    (event as { preventDefault?: () => void }).preventDefault?.();
    onShowContextMenu(window);
  });
  if (platform === "win32") {
    window.hookWindowMessage(windowsNonClientLeftButtonDoubleClick, onOpenPetRole);
  }
}
