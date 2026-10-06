import type { PluginServiceReference } from "@yinfengwindy/shiori-sdk";

/** Desktop-pet-owned preferences persisted by this plugin's backend. */
export type VoicePreferences = {
  enabled: boolean;
  hotkey: string;
  microphone_device_id: string;
  asr: PluginServiceReference | null;
  tts: PluginServiceReference | null;
};

/** Empty provider references stay explicit; discovery never substitutes another provider. */
export const defaultVoicePreferences: VoicePreferences = { enabled: false, hotkey: "Ctrl+Space", microphone_device_id: "", asr: null, tts: null };
