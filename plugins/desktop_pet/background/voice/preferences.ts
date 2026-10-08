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

/**
 * Whether the pet speaks replies: voice on with a TTS provider chosen. The
 * backend's `speech_on` (and so the live start gate) uses the same rule.
 */
export function speechOn(preferences: Pick<VoicePreferences, "enabled" | "tts">) {
  return preferences.enabled && Boolean(preferences.tts);
}
