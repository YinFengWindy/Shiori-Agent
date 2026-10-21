import { Chats } from "@phosphor-icons/react";
import { RoleCapabilityCard, SettingsToggleCard, roleToggleStatus, type PluginRoleSettingsContribution, type PluginRoleSettingsProps } from "@yinfengwindy/shiori-sdk";

/** A role-owned preference saved atomically with the role editor's draft. */
export function NaturalChatRoleSettings({ values, onChange }: PluginRoleSettingsProps) {
  const checked = values.enabled === true;
  return (
    <RoleCapabilityCard
      icon={<Chats className="h-5 w-5" weight="duotone" />}
      title="自然聊天"
      status={roleToggleStatus(checked)}
      control={<SettingsToggleCard checked={checked} ariaLabel="自然聊天" onChange={(enabled) => onChange({ ...values, enabled })} />}
    />
  );
}

/** Missing or newly created roles keep the existing chat presentation. */
export const naturalChatRoleSettings = {
  storage: "plugin",
  read: (state) => ({ enabled: state.enabled === true }),
  Component: NaturalChatRoleSettings,
} satisfies PluginRoleSettingsContribution;
