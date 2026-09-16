import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import type { SurfaceHandle } from "../../../apps/desktop/renderer/src/surface/pluginSurfaceRegistry";

/**
 * The pet's own right-click menu.
 *
 * Before #181 the host built this menu in `main.ts`, which meant the host had
 * to know what a desktop pet is and which of its commands belong in a menu.
 * Now the plugin owns the items and the host only knows how to pop a native
 * menu over a surface — something a transparent window's DOM cannot do,
 * because it cannot draw outside its own bounds.
 */

export const petMenuMainWindowId = "show-main-window";
export const petMenuHidePetId = "hide-pet";

export const petContextMenuItems = [
  { id: petMenuMainWindowId, label: "显示主窗口" },
  { id: petMenuHidePetId, label: "隐藏桌宠" },
];

/**
 * Opens the pet menu and performs the chosen command.
 *
 * A dismissal resolves `null` rather than hanging, so nothing here has to
 * distinguish "closed without choosing" from "still open".
 */
export async function openPetContextMenu(surface: SurfaceHandle, client: PluginRpcClient): Promise<void> {
  const choice = await surface.showContextMenu(petContextMenuItems.map((item) => ({ ...item })));
  if (choice === petMenuMainWindowId) {
    surface.activateMainWindow();
    return;
  }
  if (choice === petMenuHidePetId) await client.background.call("sync", { forceVisible: false });
}
