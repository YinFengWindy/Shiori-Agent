import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { FishSettingsPage } from "./Settings";
import { fishRoleSettings } from "./roleSettings";

/** Global connection settings and per-role sound configuration are separate contributions. */
const module: PluginUiModule = {
  pluginId: "fish_audio",
  settingsSection: { kind: "component", label: "Fish Audio", component: FishSettingsPage },
  roleSettings: fishRoleSettings,
};
export default module;
