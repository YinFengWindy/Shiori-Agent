import type { PluginUiModule } from "@shiori/plugin-sdk";
import { desktopPetRoleSettings } from "./roleSettings";
import { RolePetPackagesPanel } from "./RolePetPackagesPanel";

/**
 * The desktop pet's main-window UI contribution.
 *
 * Compiled into the host's renderer bundle by the build-time glob in
 * `apps/desktop/renderer/src/plugins/pluginUiModules.ts`. The pet has no
 * settings section and no nav page — its one piece of main-window UI is the
 * package manager, which belongs inside the role asset library the packages
 * are stored under, hence `role.assets` rather than a page of its own.
 */
const desktopPetUiModule: PluginUiModule = {
  pluginId: "desktop_pet",
  roleSettings: desktopPetRoleSettings,
  roleAssets: { component: RolePetPackagesPanel },
};

export default desktopPetUiModule;
