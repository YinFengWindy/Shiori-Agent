import { Monitor } from "@phosphor-icons/react";
import type { PluginRoleSettingsContribution, PluginRoleSettingsProps } from "../../../apps/desktop/renderer/src/plugins/pluginFeatureRegistry";
import { SettingsToggleCard } from "../../../apps/desktop/renderer/src/settings/SettingsToggleCard";
import { cardClass, cx } from "../../../apps/desktop/renderer/src/shared/styles";

/** The pet switch edits a draft; only the role editor's Save persists it. */
export function DesktopPetRoleSettings({ values, snapshot, disabled, onChange }: PluginRoleSettingsProps) {
  const checked = values.enabled === true;
  const unavailable = Boolean(disabled || (!snapshot?.available && !checked));
  return <div className={cx(cardClass, "grid content-start gap-3 p-5")}>
    <div className="flex items-center justify-between gap-3">
      <Monitor className="h-5 w-5 text-ink-muted" aria-hidden="true" />
      <SettingsToggleCard checked={checked} ariaLabel="桌宠" disabled={unavailable}
        onChange={(enabled) => onChange({ enabled })} />
    </div>
    <div className="flex items-center gap-2">
      <span className="text-sm font-semibold text-ink">桌宠</span>
      <span className="text-xs text-ink-muted">{disabled ? "桌面服务不可用" : unavailable ? "未配置桌宠" : checked ? "已启用" : "未启用"}</span>
    </div>
  </div>;
}

/** Independent plugin storage participates in the host's explicit role save. */
export const desktopPetRoleSettings: PluginRoleSettingsContribution = {
  storage: "plugin",
  read: (state) => ({ enabled: state.enabled === true }),
  Component: DesktopPetRoleSettings,
  afterSave: (values, client) => client.background.call("sync", { forceVisible: values.enabled === true }),
};
