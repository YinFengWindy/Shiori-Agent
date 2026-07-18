import type { Dispatch, SetStateAction } from "react";
import type { ScheduleTaskTrigger } from "../shared/types";
import {
  recurringScheduleOptions,
  weekdayOptions,
  type RecurringSchedulePreset,
  type RecurringScheduleRule,
} from "./roleTaskFormState";
import {
  RoleTaskFieldError,
  roleTaskFieldClass,
  roleTaskFieldLabelClass,
} from "./RoleTaskFormControls";

/** Renders the trigger-specific timing controls for a scheduled task. */
export function RoleTaskScheduleFields({
  trigger,
  when,
  recurringRule,
  saving,
  error,
  onWhenChange,
  onRecurringRuleChange,
}: {
  trigger: ScheduleTaskTrigger;
  when: string;
  recurringRule: RecurringScheduleRule;
  saving: boolean;
  error?: string;
  onWhenChange: (when: string) => void;
  onRecurringRuleChange: Dispatch<SetStateAction<RecurringScheduleRule>>;
}) {
  if (trigger !== "every") {
    const label = trigger === "at" ? "执行时间" : "延迟时长";
    return (
      <label className={roleTaskFieldLabelClass}>
        <span>{label}</span>
        <input
          className={roleTaskFieldClass}
          type={trigger === "at" ? "datetime-local" : "text"}
          placeholder={trigger === "after" ? "例如 30m、2h" : undefined}
          value={when}
          disabled={saving}
          onChange={(event) => onWhenChange(event.target.value)}
        />
        <RoleTaskFieldError message={error} />
      </label>
    );
  }

  return (
    <div className="grid gap-3">
      <label className={roleTaskFieldLabelClass}>
        <span>循环周期</span>
        <select
          className={roleTaskFieldClass}
          value={recurringRule.preset}
          disabled={saving}
          onChange={(event) => onRecurringRuleChange((current) => ({ ...current, preset: event.target.value as RecurringSchedulePreset }))}
        >
          {recurringScheduleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      {recurringRule.preset === "weekly" ? (
        <label className={roleTaskFieldLabelClass}>
          <span>星期</span>
          <select className={roleTaskFieldClass} value={recurringRule.weekday} disabled={saving} onChange={(event) => onRecurringRuleChange((current) => ({ ...current, weekday: event.target.value }))}>
            {weekdayOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
      ) : null}
      {recurringRule.preset === "daily" || recurringRule.preset === "weekly" ? (
        <label className={roleTaskFieldLabelClass}>
          <span>执行时间</span>
          <input className={roleTaskFieldClass} type="time" value={recurringRule.time} disabled={saving} onChange={(event) => onRecurringRuleChange((current) => ({ ...current, time: event.target.value }))} />
        </label>
      ) : null}
      {recurringRule.preset === "custom" ? (
        <label className={roleTaskFieldLabelClass}>
          <span>自定义规则</span>
          <input className={roleTaskFieldClass} type="text" placeholder="例如 1h 或 0 9 * * *" value={recurringRule.custom} disabled={saving} onChange={(event) => onRecurringRuleChange((current) => ({ ...current, custom: event.target.value }))} />
        </label>
      ) : null}
      <RoleTaskFieldError message={error} />
    </div>
  );
}
