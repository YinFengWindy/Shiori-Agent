import { SettingsField as Field } from "./SettingsField";
import { SettingsSectionCard, SettingsToggleField, settingsInputClass } from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { parseSettingsNumber } from "./settingsSectionUtils";

/** Renders advanced runtime settings for the selected advanced subsection. */
export function AdvancedSettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  if (subsectionId !== "general") return null;
  return (
    <SettingsSectionCard>
      <Field label="max_tokens" hint="限制单轮响应可使用的最大 token 数。">
        <input className={settingsInputClass} value={String(draft.advanced.maxTokens)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxTokens: parseSettingsNumber(event.target.value, current.advanced.maxTokens) } }))} placeholder="最大令牌数" />
      </Field>
      <Field label="max_iterations" hint="限制 Agent 单次任务允许执行的最大迭代次数。">
        <input className={settingsInputClass} value={String(draft.advanced.maxIterations)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxIterations: parseSettingsNumber(event.target.value, current.advanced.maxIterations) } }))} placeholder="最大迭代次数" />
      </Field>
      <Field label="memory_window" hint="控制上下文中保留的记忆窗口大小。">
        <input className={settingsInputClass} value={String(draft.advanced.memoryWindow)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryWindow: parseSettingsNumber(event.target.value, current.advanced.memoryWindow) } }))} placeholder="记忆窗口大小" />
      </Field>
      <Field label="memory_optimizer_interval_seconds" hint="设置记忆优化任务的执行间隔，单位为秒。">
        <input className={settingsInputClass} value={String(draft.advanced.memoryOptimizerIntervalSeconds)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerIntervalSeconds: parseSettingsNumber(event.target.value, current.advanced.memoryOptimizerIntervalSeconds) } }))} placeholder="记忆优化间隔秒数" />
      </Field>
      <SettingsToggleField label="dev_mode" hint="启用后暴露更偏开发调试的运行行为和输出。" checked={draft.advanced.devMode} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, devMode: checked } }))} />
      <SettingsToggleField label="streaming_enabled" hint="实时显示角色的 Thinking 与回复正文。" checked={draft.advanced.streamingEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, streamingEnabled: checked } }))} />
      <SettingsToggleField label="search_enabled" hint="控制 Agent 是否允许使用搜索能力。" checked={draft.advanced.searchEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, searchEnabled: checked } }))} />
      <SettingsToggleField label="spawn_enabled" hint="控制 Agent 是否允许创建子任务或派生执行流程。" checked={draft.advanced.spawnEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, spawnEnabled: checked } }))} />
      <SettingsToggleField label="memory_optimizer_enabled" hint="控制后台记忆优化任务是否启用。" checked={draft.advanced.memoryOptimizerEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerEnabled: checked } }))} />
    </SettingsSectionCard>
  );
}
