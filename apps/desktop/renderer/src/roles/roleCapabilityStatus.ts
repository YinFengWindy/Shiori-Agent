import type { SettingsFormData } from "../../../src/bridge/shared";

/** How a capability badge is tinted: working, switched off, or on but blocked by something. */
export type RoleCapabilityTone = "on" | "off" | "attention";

/** The badge a role capability card shows next to its title. */
export type RoleCapabilityStatus = { label: string; tone: RoleCapabilityTone };

/** Status of a plain on/off capability; `unavailableLabel` wins when the switch cannot be used. */
export function roleToggleStatus(checked: boolean, unavailableLabel = ""): RoleCapabilityStatus {
  if (unavailableLabel) return { label: unavailableLabel, tone: "off" };
  return checked ? { label: "已启用", tone: "on" } : { label: "未启用", tone: "off" };
}

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
