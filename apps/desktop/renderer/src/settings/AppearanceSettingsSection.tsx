import { useReducedMotion } from "motion/react";
import { updateAppearancePrefs, useAppearancePrefs } from "../shared/useAppearancePrefs";
import { SettingsGroup, SettingsToggleField, settingsGroupStackClass } from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";

/**
 * 设置 › 外观: how the app presents itself. 「实时显示回复」 is a config.toml
 * setting saved through the shared settings draft; 「看板娘」 and 「背景呼吸与
 * 视差」 are renderer-only preferences (see `shared/appearancePrefs.ts`)
 * applied the moment they change. Under the system's reduced motion the
 * ambient motion is off regardless, so its switch is shown off and locked.
 */
export function AppearanceSettingsSection({ draft, updateDraft }: Pick<SettingsSectionEditorProps, "draft" | "updateDraft">) {
  const { backdropMotion, mascot } = useAppearancePrefs();
  const reducedMotion = useReducedMotion() ?? false;
  return (
    <div className={settingsGroupStackClass} data-testid="appearance-settings">
      <SettingsGroup title="聊天">
        <SettingsToggleField
          label="实时显示回复"
          checked={draft.advanced.streamingEnabled}
          onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, streamingEnabled: checked } }))}
        />
      </SettingsGroup>
      <SettingsGroup title="界面">
        <SettingsToggleField
          label="看板娘"
          checked={mascot}
          onChange={(checked) => updateAppearancePrefs({ mascot: checked })}
        />
      </SettingsGroup>
      <SettingsGroup title="动效">
        <SettingsToggleField
          label="背景呼吸与视差"
          hint={reducedMotion ? "系统已开启减弱动态效果" : undefined}
          checked={backdropMotion && !reducedMotion}
          disabled={reducedMotion}
          onChange={(checked) => updateAppearancePrefs({ backdropMotion: checked })}
        />
      </SettingsGroup>
    </div>
  );
}
