import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { GptSoVitsSettingsPage } from "./Settings";
import { gptSoVitsRoleSettings } from "./roleSettings";

/** Independent service settings and the role voice capability card. */
const module: PluginUiModule = {
  pluginId: "gpt_sovits_tts",
  settingsSection: { kind: "component", label: "GPT-SoVITS", component: GptSoVitsSettingsPage },
  roleSettings: gptSoVitsRoleSettings,
};
export default module;
