import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { desktopPetRoleSettings } from "./roleSettings";
import { RolePetPackagesPanel } from "./RolePetPackagesPanel";
import { VoiceSettings } from "./VoiceSettings";

/**
 * The desktop pet's main-window UI contribution.
 *
 * Compiled into the host's renderer bundle by the build-time glob in
 * `apps/desktop/renderer/src/plugins/pluginUiModules.ts`. The pet has no
 * nav page; its main-window contributions are private voice settings and the
 * package manager, which belongs inside the role asset library the packages
 * are stored under, hence `role.assets` rather than a page of its own.
 */
const desktopPetUiModule: PluginUiModule = {
  pluginId: "desktop_pet",
  roleSettings: desktopPetRoleSettings,
  roleAssets: { component: RolePetPackagesPanel },
  settingsSection: { kind: "component", label: "桌宠", component: VoiceSettings },
};

export default desktopPetUiModule;
