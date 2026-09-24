import { SettingsField as Field } from "./SettingsField";
import { SettingsSectionCard, settingsInputClass } from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";

/** Renders channel credentials for the selected channel subsection. */
export function ChannelsSettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  switch (subsectionId) {
    case "qq":
      return (
        <SettingsSectionCard>
          <Field label="Bot QQ号" hint="填入Bot 的QQ号；留空则不启用 QQ 渠道。">
            <input className={settingsInputClass} value={draft.channels.qqBotUin} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqBotUin: event.target.value } }))} />
          </Field>
        </SettingsSectionCard>
      );
    default:
      return null;
  }
}
