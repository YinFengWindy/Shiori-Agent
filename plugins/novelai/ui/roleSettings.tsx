import { ImageSquare } from "@phosphor-icons/react";
import { SettingsToggleField } from "../../../apps/desktop/renderer/src/settings/SettingsFieldPrimitives";
import { cardClass, cx } from "../../../apps/desktop/renderer/src/shared/styles";
import type { PluginRoleSettingsContribution, PluginRoleSettingsProps } from "../../../apps/desktop/renderer/src/plugins/pluginFeatureRegistry";

/** NovelAI's per-role preference stays independent of the global plugin enable switch. */
export function NovelAiRoleSettings({ values, onChange }: PluginRoleSettingsProps) {
  return <div className={cx(cardClass, "p-5")}>
    <ImageSquare className="mb-3 h-5 w-5 text-ink-muted" aria-hidden="true" />
    <SettingsToggleField label="自动场景 CG" checked={Boolean(values.autoSceneCgEnabled)}
      onChange={(checked) => onChange({ ...values, autoSceneCgEnabled: checked })} />
  </div>;
}

/** The CG preference participates in the role editor’s atomic plugin draft save. */
export const novelAiRoleSettings = {
  storage: "plugin",
  read: (state) => ({ autoSceneCgEnabled: state.autoSceneCgEnabled === true }),
  Component: NovelAiRoleSettings,
} satisfies PluginRoleSettingsContribution;
