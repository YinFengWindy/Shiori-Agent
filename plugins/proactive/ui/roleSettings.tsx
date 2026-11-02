import { BellRinging } from "@phosphor-icons/react";
import { RoleCapabilityCard, SettingsToggleCard, roleToggleStatus, type PluginRoleSettingsContribution, type PluginRoleSettingsProps, type PluginRoleValues } from "@yinfengwindy/shiori-sdk";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";
import { readRoleProactiveForm } from "./roleProactiveDefaults";

/** Existing proactive card, bound to the plugin's shared role draft. */
export function ProactiveRoleSettings({ values, onChange, disabled, devMode }: PluginRoleSettingsProps) {
  const form = readRoleProactiveForm(values);
  return <RoleCapabilityCard
    icon={<BellRinging className="h-5 w-5" weight="duotone" />}
    title="主动推送"
    status={roleToggleStatus(form.proactiveEnabled)}
    data-testid="role-proactive-capability"
    control={<SettingsToggleCard checked={form.proactiveEnabled} disabled={disabled} ariaLabel="主动推送" onChange={(checked) => onChange({ ...form, proactiveEnabled: checked })} />}
    settings={<RoleProactiveSettingsPanel devMode={devMode} roleForm={form} onUpdate={(next) => onChange(typeof next === "function" ? next(form) : next)} />}
  />;
}

/** Saves edited values through the plugin RPC after the core role save. */
export const proactiveRoleSettings = {
  storage: "plugin",
  Component: ProactiveRoleSettings,
  read: readRoleProactiveForm,
  async save(roleId, values, previous, client) {
    const patch = Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== previous[key]));
    return client.call<PluginRoleValues>("settings_set", { role_id: roleId, values: patch });
  },
} satisfies PluginRoleSettingsContribution;
