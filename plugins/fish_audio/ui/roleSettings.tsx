import { WaveformIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { RoleCapabilityCard, type PluginRoleSettingsContribution, type PluginRoleSettingsProps } from "@yinfengwindy/shiori-sdk";
import { useRoleVoice } from "./useRoleVoice";
import { RoleVoiceEditor } from "./RoleVoiceEditor";

/** A role-owned sound card; credentials stay on the plugin settings page. */
export function FishRoleCard({ roleId, client, disabled }: PluginRoleSettingsProps) {
  const [open, setOpen] = useState(false);
  const voice = useRoleVoice(client, roleId);
  const status = !roleId ? { label: "未保存角色", tone: "off" as const }
    : voice.loadError ? { label: "读取失败", tone: "attention" as const }
    : !voice.saved ? { label: "读取中", tone: "off" as const }
    : voice.saved.reference_id ? { label: "已配置", tone: "on" as const }
    : { label: "未设置声音", tone: "off" as const };
  return <RoleCapabilityCard icon={<WaveformIcon className="h-5 w-5" weight="duotone" />} title="Fish Audio 声音" status={status}
    onSettingsOpenChange={(next) => { setOpen(next); if (!next) voice.commit(); }}
    settings={<RoleVoiceEditor key={roleId} client={client} roleId={roleId} active={open} voice={voice} disabled={disabled === true} />} />;
}

/** Sound settings remain in plugin storage, never in roles.update payloads. */
export const fishRoleSettings: PluginRoleSettingsContribution = { storage: "plugin", read: () => ({}), Component: FishRoleCard };
