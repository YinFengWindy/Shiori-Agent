import type { RoleCapabilityStatus } from "@shiori/plugin-sdk";
import type { SettingsFormData } from "../../../src/bridge/shared";

/*
 * The badge vocabulary and `roleToggleStatus` are owned by
 * `@shiori/plugin-sdk` (#440) and re-exported here; the voice statuses below
 * read host settings and stay host-only.
 */
export { roleToggleStatus, type RoleCapabilityStatus, type RoleCapabilityTone } from "@shiori/plugin-sdk";

/**
 * Whether spoken replies are on globally: the desktop voice switch and the
 * TTS provider switch (which falls back to the voice switch when unset, as
 * the settings writer does). Null while the settings are not read yet.
 */
export function globalVoiceOutputEnabled(settings: Pick<SettingsFormData, "voice"> | null): boolean | null {
  if (!settings) return null;
  return settings.voice.enabled && (settings.voice.ttsEnabled ?? settings.voice.enabled);
}

type RoleVoiceStatusInput = {
  roleEnabled: boolean;
  voiceId: string;
  /** Global voice output; null while unknown, which never blocks the badge. */
  globalEnabled: boolean | null;
};

/**
 * The role voice badge reflects whether the role will actually speak: its own
 * switch first, then the global voice switch, then a chosen voice. Only when
 * all three hold does it read 已启用.
 */
export function roleVoiceStatus({ roleEnabled, voiceId, globalEnabled }: RoleVoiceStatusInput): RoleCapabilityStatus {
  if (!roleEnabled) return { label: "未启用", tone: "off" };
  if (globalEnabled === false) return { label: "全局语音已关闭", tone: "attention" };
  if (!voiceId.trim()) return { label: "未设置音色", tone: "attention" };
  return { label: "已启用", tone: "on" };
}
