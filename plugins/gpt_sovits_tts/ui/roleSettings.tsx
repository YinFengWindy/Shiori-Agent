import { WaveformIcon } from "@phosphor-icons/react";
import { RoleCapabilityCard, type PluginRoleSettingsContribution, type PluginRoleSettingsProps, type RoleCapabilityStatus } from "@yinfengwindy/shiori-sdk";
import { RoleVoiceEditor } from "./RoleVoiceEditor";
import { useRoleVoice, type RoleVoiceAutosave } from "./useRoleVoice";

/** The card badge: whether the role has the default reference every synthesis needs. */
export function roleVoiceStatus(voice: Pick<RoleVoiceAutosave, "draft" | "loadError">): RoleCapabilityStatus {
  if (voice.loadError) return { label: "读取失败", tone: "attention" };
  return voice.draft?.default ? { label: "已配置", tone: "on" } : { label: "未设置默认参考", tone: "off" };
}

/**
 * The 「GPT-SoVITS 声音」 capability card. It has no switch and no role draft
 * values: its ⚙ dialog edits this plugin's private role voice, which autosaves
 * on its own instead of following the role editor's Save.
 */
export function GptSoVitsRoleCard({ roleId, client, moodCatalog, disabled }: PluginRoleSettingsProps) {
  const voice = useRoleVoice(client, roleId);
  return <RoleCapabilityCard
    icon={<WaveformIcon className="h-5 w-5" weight="duotone" />}
    title="GPT-SoVITS 声音"
    status={roleVoiceStatus(voice)}
    data-testid="gpt-sovits-voice-capability"
    settings={<RoleVoiceEditor roleId={roleId} client={client} voice={voice} moodCatalog={moodCatalog} disabled={disabled === true} />}
  />;
}

/** Plugin storage with no values: nothing joins the role draft, dirty state or `roles.update`. */
export const gptSoVitsRoleSettings: PluginRoleSettingsContribution = {
  storage: "plugin",
  read: () => ({}),
  Component: GptSoVitsRoleCard,
};
