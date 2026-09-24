import type React from "react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleFormState } from "../shared/types";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";
import { roleProactiveDefaults } from "./roleProactiveDefaults";

type NumberField =
  | "proactiveAgentMaxSteps"
  | "proactiveAgentContentLimit"
  | "proactiveAgentWebFetchMaxChars"
  | "proactiveDriftMaxSteps"
  | "proactiveDriftMinIntervalHours";

type RoleProactiveExecutionFieldsProps = {
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** The folded 执行参数 of proactive push: per-push limits, then idle activity (drift) and its limits. */
export function RoleProactiveExecutionFields({ roleForm, onUpdate }: RoleProactiveExecutionFieldsProps) {
  const numberInput = (label: string, field: NumberField, fallback: number) => (
    <label className={roleFieldLabelClass}>
      <span>{label}</span>
      <input
        className={roleFieldClass}
        inputMode="numeric"
        value={String(roleForm[field] ?? fallback)}
        onChange={(event) => onUpdate((current) => ({ ...current, [field]: parseNumber(event.target.value, fallback) }))}
      />
    </label>
  );

  return (
    <div className="grid gap-5 border-t border-line-soft pt-4">
      <div className="grid gap-4 sm:grid-cols-3">
        {numberInput("每次推送最大步数", "proactiveAgentMaxSteps", roleProactiveDefaults.agentMaxSteps)}
        {numberInput("候选内容数", "proactiveAgentContentLimit", roleProactiveDefaults.agentContentLimit)}
        {numberInput("网页上下文字符数", "proactiveAgentWebFetchMaxChars", roleProactiveDefaults.agentWebFetchMaxChars)}
      </div>
      <div className="grid gap-4 border-t border-line-soft pt-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="m-0 text-body-sm font-medium text-ink">空闲活动</h3>
          <SettingsToggleCard
            checked={Boolean(roleForm.proactiveDriftEnabled ?? roleProactiveDefaults.driftEnabled)}
            ariaLabel="空闲活动"
            onChange={(checked) => onUpdate((current) => ({ ...current, proactiveDriftEnabled: checked }))}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {numberInput("空闲活动最大步数", "proactiveDriftMaxSteps", roleProactiveDefaults.driftMaxSteps)}
          {numberInput("空闲活动最小间隔（小时）", "proactiveDriftMinIntervalHours", roleProactiveDefaults.driftMinIntervalHours)}
        </div>
      </div>
    </div>
  );
}
