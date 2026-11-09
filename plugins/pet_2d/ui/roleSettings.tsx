import { useState } from "react";
import { SlidersHorizontal } from "@phosphor-icons/react";
import { RoleCapabilityCard, usePluginHostServices, type PluginRoleSettingsContribution, type PluginRoleSettingsProps } from "@yinfengwindy/shiori-sdk";
import { AnimationSettings } from "./AnimationSettings";

/** Animation belongs next to the edited role; package files remain immutable. */
export function AvatarRoleSettings({ roleId, client, disabled }: PluginRoleSettingsProps) {
  const host = usePluginHostServices(), [open, setOpen] = useState(false);
  return <RoleCapabilityCard icon={<SlidersHorizontal className="h-5 w-5" weight="duotone" />} title="2.5D 动画"
    status={{ label: disabled ? "不可用" : roleId ? "按形象保存" : "未保存角色", tone: "off" }}
    onSettingsOpenChange={setOpen}
    settings={open && roleId && !disabled ? <AnimationSettings key={roleId} roleId={roleId} client={client} host={host} /> : <span className="text-body-sm text-ink-muted">{disabled ? "桌面服务不可用" : "请先保存角色"}</span>} />;
}
/** Parameters autosave privately; the role's explicit save has no animation draft. */
export const avatarRoleSettings: PluginRoleSettingsContribution = { storage: "plugin", read: () => ({}), Component: AvatarRoleSettings };
