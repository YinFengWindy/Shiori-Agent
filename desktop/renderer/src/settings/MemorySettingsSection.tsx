import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  SettingsToggleField,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { getMemoryEngineOptions } from "./settingsSectionUtils";
import { cx, inputClass } from "../shared/styles";

/** Renders memory and embedding settings for the selected memory subsection. */
export function MemorySettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  switch (subsectionId) {
    case "general":
      return (
        <SettingsSectionCard>
          <SettingsToggleField label="启用记忆" checked={draft.memory.enabled} onChange={(checked) => updateDraft((current) => ({ ...current, memory: { ...current.memory, enabled: checked } }))} />
          <Field label="记忆引擎" hint="default 对应 default_memory 插件。">
            <select className={cx(inputClass, "bg-white")} value={draft.memory.engine} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, engine: event.target.value } }))}>
              {getMemoryEngineOptions(draft.memory.engine).map((option) => (
                <option key={option.value || "default"} value={option.value}>{option.label}</option>
              ))}
            </select>
          </Field>
        </SettingsSectionCard>
      );
    case "embedding":
      return (
        <SettingsSectionCard>
          <Field label="Embedding 模型">
            <input className={cx(inputClass, "bg-white")} value={draft.memory.embeddingModel} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingModel: event.target.value } }))} />
          </Field>
          <Field label="API Key">
            <SettingsSecretInput value={draft.memory.embeddingApiKey} onChange={(value) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingApiKey: value } }))} />
          </Field>
          <Field label="Base URL">
            <input className={cx(inputClass, "bg-white")} value={draft.memory.embeddingBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingBaseUrl: event.target.value } }))} />
          </Field>
          <Field label="输出维度">
            <input className={cx(inputClass, "bg-white")} value={draft.memory.outputDimensionality} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, outputDimensionality: event.target.value } }))} />
          </Field>
        </SettingsSectionCard>
      );
    default:
      return null;
  }
}
