import { WaveformIcon } from "@phosphor-icons/react";
import { RoleCapabilityCard, type PluginRoleSettingsContribution, type PluginRoleSettingsProps, type RoleCapabilityStatus } from "@yinfengwindy/shiori-sdk";
import { RoleVoiceEditor } from "./RoleVoiceEditor";
import { useRoleVoice, type RoleVoiceAutosave } from "./useRoleVoice";

/**
 * The card badge, from the stored document rather than the draft: whether the
 * role has the default reference every synthesis needs. A role not saved yet
 * or a document still loading shows a neutral state.
 */
export function roleVoiceStatus(roleId: string | null, voice: Pick<RoleVoiceAutosave, "saved" | "loadError">): RoleCapabilityStatus {
  if (roleId === null) return { label: "未保存角色", tone: "off" };
  if (voice.loadError) return { label: "读取失败", tone: "attention" };
  if (!voice.saved) return { label: "读取中", tone: "off" };
  return voice.saved.default ? { label: "已配置", tone: "on" } : { label: "未设置默认参考", tone: "off" };
}

/**
 * The 「GPT-SoVITS 声音」 capability card. It has no switch and no role draft
 * values: its ⚙ dialog edits this plugin's private role voice, which autosaves
 * on its own instead of following the role editor's Save; closing the dialog
 * submits the last edit at once.
 */
export function GptSoVitsRoleCard({ roleId, client, moodCatalog, disabled }: PluginRoleSettingsProps) {
  const voice = useRoleVoice(client, roleId);
  return <RoleCapabilityCard
    icon={<WaveformIcon className="h-5 w-5" weight="duotone" />}
    title="GPT-SoVITS 声音"
    status={roleVoiceStatus(roleId, voice)}
    data-testid="gpt-sovits-voice-capability"
    onSettingsOpenChange={(open) => { if (!open) voice.commit(); }}
    settings={<RoleVoiceEditor roleId={roleId} client={client} voice={voice} moodCatalog={moodCatalog} disabled={disabled === true} />}
  />;
}

/** Plugin storage with no values: nothing joins the role draft, dirty state or `roles.update`. */
export const gptSoVitsRoleSettings: PluginRoleSettingsContribution = {
  storage: "plugin",
  read: () => ({}),
  Component: GptSoVitsRoleCard,
};
