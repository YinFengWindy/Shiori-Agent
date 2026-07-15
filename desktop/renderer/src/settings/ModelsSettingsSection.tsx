import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  SettingsToggleField,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { cx, inputClass } from "../shared/styles";

/** Renders model-provider settings for the selected model subsection. */
export function ModelsSettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  switch (subsectionId) {
    case "main":
      return (
        <SettingsSectionCard>
          <Field label="Provider" hint="当前主模型提供商。">
            <input className={cx(inputClass, "bg-white")} value={draft.models.provider} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, provider: event.target.value } }))} />
          </Field>
          <Field label="主模型" hint="对话使用的模型。">
            <input className={cx(inputClass, "bg-white")} value={draft.models.mainModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainModel: event.target.value } }))} />
          </Field>
          <Field label="API Key">
            <SettingsSecretInput value={draft.models.mainApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, mainApiKey: value } }))} />
          </Field>
          <Field label="Base URL">
            <input className={cx(inputClass, "bg-white")} value={draft.models.mainBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainBaseUrl: event.target.value } }))} />
          </Field>
          <Field label="Reasoning Effort" hint="支持的模型可用，用于控制推理强度；留空表示不写入。">
            <input className={cx(inputClass, "bg-white")} value={draft.models.reasoningEffort} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, reasoningEffort: event.target.value } }))} placeholder="例如 low / medium / high" />
          </Field>
          <SettingsToggleField label="启用 Thinking" checked={draft.models.enableThinking} onChange={(checked) => updateDraft((current) => ({ ...current, models: { ...current.models, enableThinking: checked } }))} />
          <SettingsToggleField label="启用多模态" checked={draft.models.multimodal} onChange={(checked) => updateDraft((current) => ({ ...current, models: { ...current.models, multimodal: checked } }))} />
        </SettingsSectionCard>
      );
    case "fast":
      return (
        <SettingsSectionCard>
          <Field label="轻量模型" hint="轻量任务时使用的模型名；留空时则沿用主模型。">
            <input className={cx(inputClass, "bg-white")} value={draft.models.fastModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastModel: event.target.value } }))} placeholder="模型名" />
          </Field>
          <Field label="API Key">
            <SettingsSecretInput value={draft.models.fastApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, fastApiKey: value } }))} />
          </Field>
          <Field label="Base URL">
            <input className={cx(inputClass, "bg-white")} value={draft.models.fastBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastBaseUrl: event.target.value } }))} placeholder="基础地址" />
          </Field>
        </SettingsSectionCard>
      );
    case "agent":
      return (
        <SettingsSectionCard>
          <Field label="Agent 模型" hint="用于工具调用和角色主动任务；留空时沿用主模型。">
            <input className={cx(inputClass, "bg-white")} value={draft.models.agentModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentModel: event.target.value } }))} placeholder="模型名" />
          </Field>
          <Field label="API Key">
            <SettingsSecretInput value={draft.models.agentApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, agentApiKey: value } }))} />
          </Field>
          <Field label="Base URL">
            <input className={cx(inputClass, "bg-white")} value={draft.models.agentBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentBaseUrl: event.target.value } }))} placeholder="基础地址" />
          </Field>
        </SettingsSectionCard>
      );
    case "vl":
      return (
        <SettingsSectionCard>
          <Field label="视觉模型" hint="若主模型未启动多模态，则使用该模型；留空时则沿用主模型。">
            <input className={cx(inputClass, "bg-white")} value={draft.models.vlModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlModel: event.target.value } }))} placeholder="模型名" />
          </Field>
          <Field label="API Key" hint="">
            <SettingsSecretInput value={draft.models.vlApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, vlApiKey: value } }))} />
          </Field>
          <Field label="Base URL" hint="">
            <input className={cx(inputClass, "bg-white")} value={draft.models.vlBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlBaseUrl: event.target.value } }))} placeholder="基础地址" />
          </Field>
        </SettingsSectionCard>
      );
    default:
      return null;
  }
}
