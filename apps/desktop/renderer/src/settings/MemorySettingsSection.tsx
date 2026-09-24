import { Select } from "../shared/ui/Select";
import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  SettingsToggleField,
  settingsInputClass,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { getMemoryEngineOptions } from "./settingsSectionUtils";
import { cx } from "../shared/styles";

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
          <Field label="记忆引擎">
            <Select aria-label="记忆引擎" className={settingsInputClass} value={draft.memory.engine} onValueChange={(value) => updateDraft((current) => ({ ...current, memory: { ...current.memory, engine: value } }))} options={getMemoryEngineOptions(draft.memory.engine)} />
          </Field>
        </SettingsSectionCard>
      );
    case "embedding":
      return (
        <SettingsSectionCard>
          <Field label="模型">
            <input aria-label="向量模型" className={settingsInputClass} placeholder="text-embedding-v4" value={draft.memory.embeddingModel} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingModel: event.target.value } }))} />
          </Field>
          <Field label="API Key">
            <SettingsSecretInput ariaLabel="API Key" value={draft.memory.embeddingApiKey} onChange={(value) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingApiKey: value } }))} />
          </Field>
          <Field label="Base URL">
            <input aria-label="Base URL" className={settingsInputClass} placeholder="https://example.com/v1" value={draft.memory.embeddingBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingBaseUrl: event.target.value } }))} />
          </Field>
          <Field label="输出维度">
            <input aria-label="输出维度" className={cx(settingsInputClass, "tabular-nums")} inputMode="numeric" placeholder="1024" value={draft.memory.outputDimensionality} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, outputDimensionality: event.target.value } }))} />
          </Field>
        </SettingsSectionCard>
      );
    default:
      return null;
  }
}
