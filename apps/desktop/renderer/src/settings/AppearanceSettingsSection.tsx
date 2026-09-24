import { useReducedMotion } from "motion/react";
import { updateAppearancePrefs, useAppearancePrefs } from "../shared/useAppearancePrefs";
import { SettingsSectionCard, SettingsToggleField } from "./SettingsFieldPrimitives";

/**
 * 设置 › 外观: renderer-only display preferences (see `shared/appearancePrefs.ts`),
 * applied the moment they change — no save step. Under the system's reduced
 * motion the ambient motion is off regardless, so its switch is shown off and
 * locked.
 */
export function AppearanceSettingsSection() {
  const { backdropMotion } = useAppearancePrefs();
  const reducedMotion = useReducedMotion() ?? false;
  return (
    <div data-testid="appearance-settings">
      <SettingsSectionCard>
        <SettingsToggleField
          label="背景呼吸与视差"
          hint={reducedMotion ? "系统已开启减弱动态效果" : undefined}
          checked={backdropMotion && !reducedMotion}
          disabled={reducedMotion}
          onChange={(checked) => updateAppearancePrefs({ backdropMotion: checked })}
        />
      </SettingsSectionCard>
    </div>
  );
}
