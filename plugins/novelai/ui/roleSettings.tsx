import { ImageSquare } from "@phosphor-icons/react";
import type { PluginRoleSettingsContribution, PluginRoleSettingsProps } from "../../../apps/desktop/renderer/src/plugins/pluginFeatureRegistry";
import { RoleCapabilityCard } from "../../../apps/desktop/renderer/src/roles/RoleCapabilityCard";
import { roleToggleStatus } from "../../../apps/desktop/renderer/src/roles/roleCapabilityStatus";
import { SettingsToggleCard } from "../../../apps/desktop/renderer/src/settings/SettingsToggleCard";

/** NovelAI's per-role preference stays independent of the global plugin enable switch. */
export function NovelAiRoleSettings({ values, onChange }: PluginRoleSettingsProps) {
  const checked = Boolean(values.autoSceneCgEnabled);
  return (
    <RoleCapabilityCard
      icon={<ImageSquare className="h-5 w-5" weight="duotone" />}
      title="自动场景 CG"
      status={roleToggleStatus(checked)}
      control={<SettingsToggleCard checked={checked} ariaLabel="自动场景 CG" onChange={(autoSceneCgEnabled) => onChange({ ...values, autoSceneCgEnabled })} />}
    />
  );
}

/** The CG preference participates in the role editor’s atomic plugin draft save. */
export const novelAiRoleSettings = {
  storage: "plugin",
  read: (state) => ({ autoSceneCgEnabled: state.autoSceneCgEnabled === true }),
  Component: NovelAiRoleSettings,
} satisfies PluginRoleSettingsContribution;
