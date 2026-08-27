import { SettingsField as Field } from "./SettingsField";
import { SettingsSecretInput, SettingsSectionCard, settingsInputClass } from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";

/** Renders channel credentials for the selected channel subsection. */
export function ChannelsSettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  switch (subsectionId) {
    case "telegram":
      return (
        <SettingsSectionCard>
          <Field label="Telegram Token">
            <SettingsSecretInput value={draft.channels.telegramToken} onChange={(value) => updateDraft((current) => ({ ...current, channels: { ...current.channels, telegramToken: value } }))} />
          </Field>
        </SettingsSectionCard>
      );
    case "qq":
      return (
        <SettingsSectionCard>
          <Field label="Bot QQ号" hint="填入Bot 的QQ号；留空则不启用 QQ 渠道。">
            <input className={settingsInputClass} value={draft.channels.qqBotUin} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqBotUin: event.target.value } }))} />
          </Field>
        </SettingsSectionCard>
      );
    case "qqbot":
      return (
        <SettingsSectionCard>
          <Field label="App ID">
            <input
              className={settingsInputClass}
              value={draft.channels.qqBotAppId}
              onChange={(event) => updateDraft((current) => ({
                ...current,
                channels: { ...current.channels, qqBotAppId: event.target.value },
              }))}
            />
          </Field>
          <Field label="Client Secret">
            <SettingsSecretInput
              value={draft.channels.qqBotClientSecret}
              onChange={(value) => updateDraft((current) => ({
                ...current,
                channels: { ...current.channels, qqBotClientSecret: value },
              }))}
            />
          </Field>
        </SettingsSectionCard>
      );
    default:
      return null;
  }
}
