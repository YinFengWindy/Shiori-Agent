import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { SenseVoiceSettingsPage } from "./Settings";

/** Standalone ASR settings and file transcription tools. */
const module: PluginUiModule = { pluginId: "sensevoice_asr", settingsSection: { kind: "component", label: "SenseVoiceSmall", component: SenseVoiceSettingsPage } };
export default module;
