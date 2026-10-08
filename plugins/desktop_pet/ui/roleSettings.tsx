import { Monitor } from "@phosphor-icons/react";
import {
  RoleCapabilityCard,
  roleToggleStatus,
  SettingsToggleCard,
  type PluginRoleSettingsContribution,
  type PluginRoleSettingsProps,
} from "@yinfengwindy/shiori-sdk";

/** The pet switch edits a draft; only the role editor's Save persists it. */
export function DesktopPetRoleSettings({ values, snapshot, disabled, onChange }: PluginRoleSettingsProps) {
  const checked = values.enabled === true;
  const unavailable = Boolean(disabled || (!snapshot?.available && !checked));
  const unavailableLabel = disabled ? "桌面服务不可用" : unavailable ? "未配置桌宠" : "";
  return (
    <RoleCapabilityCard
      icon={<Monitor className="h-5 w-5" weight="duotone" />}
      title="桌宠"
      status={roleToggleStatus(checked, unavailableLabel)}
      control={<SettingsToggleCard checked={checked} ariaLabel="桌宠" disabled={unavailable} onChange={(enabled) => onChange({ enabled })} />}
    />
  );
}

/** Independent plugin storage participates in the host's explicit role save. */
export const desktopPetRoleSettings: PluginRoleSettingsContribution = {
  storage: "plugin",
  read: (state) => ({ enabled: state.enabled === true }),
  Component: DesktopPetRoleSettings,
  afterSave: (values, client) => client.background.call("sync", { forceVisible: values.enabled === true }),
};
