import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  SettingsToggleField,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { parseSettingsNumber } from "./settingsSectionUtils";

/** Renders third-party integration settings for the selected integration subsection. */
export function IntegrationsSettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  if (subsectionId !== "novelai") return null;
  return (
    <SettingsSectionCard>
      <SettingsToggleField label="启用 NovelAI" checked={draft.integrations.novelaiEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiEnabled: checked } }))} />
      <Field label="Token">
        <SettingsSecretInput value={draft.integrations.novelaiToken} onChange={(value) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiToken: value } }))} />
      </Field>
      <SettingsToggleField label="Add Quality Tags" checked={draft.integrations.novelaiAddQualityTags} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAddQualityTags: checked } }))} />
      <Field label="内容过滤预设" hint="控制默认 undesired content 强度。">
        <select
          className="h-12 w-full rounded-md border border-[#D8DCE2] bg-[#F3F5F7] px-3.5 text-sm leading-5 text-[#1f1f1f] transition focus:border-[#D8DCE2] focus:outline-none focus-visible:border-[#D8DCE2] focus-visible:outline-none"
          value={String(draft.integrations.novelaiUndesiredContentPreset)}
          onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiUndesiredContentPreset: parseSettingsNumber(event.target.value, current.integrations.novelaiUndesiredContentPreset) } }))}
        >
          <option value="0">Undesired Content Preset: None</option>
          <option value="1">Undesired Content Preset: Light</option>
          <option value="2">Undesired Content Preset: Heavy</option>
        </select>
      </Field>
      <SettingsToggleField label="生成后自动写回角色素材" checked={draft.integrations.novelaiAutoWritebackRoleAssets} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAutoWritebackRoleAssets: checked } }))} />
      <SettingsToggleField label="NSFW 模式（开启时使用 Full）" checked={draft.integrations.novelaiNsfwEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiNsfwEnabled: checked } }))} />
    </SettingsSectionCard>
  );
}
