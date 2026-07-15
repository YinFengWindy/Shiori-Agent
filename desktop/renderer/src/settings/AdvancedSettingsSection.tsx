import { SettingsField as Field } from "./SettingsField";
import { SettingsSectionCard, SettingsToggleField } from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { parseSettingsNumber } from "./settingsSectionUtils";
import { cx, inputClass, textareaClass } from "../shared/styles";

/** Renders advanced runtime settings for the selected advanced subsection. */
export function AdvancedSettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  if (subsectionId !== "general") return null;
  return (
    <SettingsSectionCard>
      <Field label="System Prompt" hint="全局系统提示词">
        <textarea className={cx(textareaClass, "min-h-28 bg-white")} value={draft.advanced.systemPrompt} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, systemPrompt: event.target.value } }))} />
      </Field>
      <Field label="max_tokens" hint="限制单轮响应可使用的最大 token 数。">
        <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.maxTokens)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxTokens: parseSettingsNumber(event.target.value, current.advanced.maxTokens) } }))} placeholder="最大令牌数" />
      </Field>
      <Field label="max_iterations" hint="限制 Agent 单次任务允许执行的最大迭代次数。">
        <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.maxIterations)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxIterations: parseSettingsNumber(event.target.value, current.advanced.maxIterations) } }))} placeholder="最大迭代次数" />
      </Field>
      <Field label="memory_window" hint="控制上下文中保留的记忆窗口大小。">
        <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.memoryWindow)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryWindow: parseSettingsNumber(event.target.value, current.advanced.memoryWindow) } }))} placeholder="记忆窗口大小" />
      </Field>
      <Field label="memory_optimizer_interval_seconds" hint="设置记忆优化任务的执行间隔，单位为秒。">
        <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.memoryOptimizerIntervalSeconds)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerIntervalSeconds: parseSettingsNumber(event.target.value, current.advanced.memoryOptimizerIntervalSeconds) } }))} placeholder="记忆优化间隔秒数" />
      </Field>
      <SettingsToggleField label="dev_mode" hint="启用后暴露更偏开发调试的运行行为和输出。" checked={draft.advanced.devMode} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, devMode: checked } }))} />
      <SettingsToggleField label="search_enabled" hint="控制 Agent 是否允许使用搜索能力。" checked={draft.advanced.searchEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, searchEnabled: checked } }))} />
      <SettingsToggleField label="spawn_enabled" hint="控制 Agent 是否允许创建子任务或派生执行流程。" checked={draft.advanced.spawnEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, spawnEnabled: checked } }))} />
      <SettingsToggleField label="memory_optimizer_enabled" hint="控制后台记忆优化任务是否启用。" checked={draft.advanced.memoryOptimizerEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerEnabled: checked } }))} />
    </SettingsSectionCard>
  );
}
