import { ImageSquare } from "@phosphor-icons/react";
import { RoleCapabilityCard, SettingsToggleCard, roleToggleStatus, type PluginRoleSettingsContribution, type PluginRoleSettingsProps } from "@yinfengwindy/shiori-sdk";
import { AutoCgPromptSettingsEditor } from "./AutoCgPromptSettingsEditor";
import { useAutoCgPromptSettings } from "./useAutoCgPromptSettings";

/** NovelAI's per-role preference stays independent of the global plugin enable switch. */
export function NovelAiRoleSettings({ roleId, client, values, disabled, onChange }: PluginRoleSettingsProps) {
  const settings = useAutoCgPromptSettings(client, roleId);
  const checked = Boolean(values.autoSceneCgEnabled);
  return (
    <RoleCapabilityCard
      icon={<ImageSquare className="h-5 w-5" weight="duotone" />}
      title="自动场景 CG"
      status={roleToggleStatus(checked)}
      control={<SettingsToggleCard checked={checked} ariaLabel="自动场景 CG" disabled={disabled} onChange={(autoSceneCgEnabled) => onChange({ ...values, autoSceneCgEnabled })} />}
      onSettingsOpenChange={(open) => { if (!open) settings.commit(); }}
      settings={<AutoCgPromptSettingsEditor roleId={roleId} settings={settings} disabled={disabled === true} />}
    />
  );
}

/** The CG preference participates in the role editor’s atomic plugin draft save. */
export const novelAiRoleSettings = {
  storage: "plugin",
  read: (state) => ({ autoSceneCgEnabled: state.autoSceneCgEnabled === true }),
  Component: NovelAiRoleSettings,
} satisfies PluginRoleSettingsContribution;
