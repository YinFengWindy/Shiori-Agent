import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { GptSoVitsSettingsPage } from "./Settings";
import { RoleVoiceEditor } from "./RoleVoiceEditor";

/** Independent service settings and private role voice editing. */
const module: PluginUiModule = {
  pluginId: "gpt_sovits_tts",
  settingsSection: { kind: "component", label: "GPT-SoVITS", component: GptSoVitsSettingsPage },
  roleUi: { mode: "self-managed", Component: RoleVoiceEditor },
};
export default module;
