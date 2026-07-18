import { ArrowLeft } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";
import type { ScheduleTaskFormData, ScheduleTaskTier, ScheduleTaskTrigger } from "../shared/types";
import { cx, focusResetClass } from "../shared/styles";
import {
  buildRecurringScheduleRule,
  parseRecurringScheduleRule,
  recurringScheduleOptions,
  validateScheduleTaskForm,
  weekdayOptions,
  type RecurringSchedulePreset,
  type ScheduleTaskFormErrors,
} from "./roleTaskFormState";
import {
  chatSidebarBackButtonClass,
  chatSidebarHeaderClass,
  chatSidebarPanelClass,
  chatSidebarScrollableClass,
} from "./chatSidebarStyles";

const fieldClass =
  "w-full rounded-md border border-[#D8DFE7] bg-white px-3 py-2 text-sm transition focus:border-[#B8C2CE] focus:outline-none disabled:opacity-60";

function FieldError({ message }: { message?: string }) {
  return message ? <span className="text-[11px] text-[#B42318]">{message}</span> : null;
}

/** Renders the create/edit form for a scheduled role task. */
export function RoleTaskForm({ title, initialData, saving, error, onBack, onSave }: {
  title: string;
  initialData: ScheduleTaskFormData;
  saving: boolean;
  error: string;
  onBack: () => void;
  onSave: (data: ScheduleTaskFormData) => Promise<void>;
}) {
  const [data, setData] = useState(initialData);
  const [recurringRule, setRecurringRule] = useState(() => parseRecurringScheduleRule(initialData.when));
  const [errors, setErrors] = useState<ScheduleTaskFormErrors>({});

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const submittedData = data.trigger === "every" ? { ...data, when: buildRecurringScheduleRule(recurringRule) } : data;
    const nextErrors = validateScheduleTaskForm(submittedData);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    try {
      await onSave(submittedData);
    } catch {
      return;
    }
  };

  const whenLabel = data.trigger === "at" ? "执行时间" : "延迟时长";
  const whenPlaceholder = data.trigger === "after" ? "例如 30m、2h" : "例如 1h 或 0 9 * * *";

  return (
    <form className={cx(chatSidebarPanelClass, "grid-rows-[auto_minmax(0,1fr)_auto]")} onSubmit={(event) => void submit(event)}>
      <div className={cx(chatSidebarHeaderClass, "gap-2")}>
        <button className={chatSidebarBackButtonClass} type="button" aria-label="返回" disabled={saving} onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="font-semibold text-[#272536]">{title}</span>
      </div>
      <div className={cx(chatSidebarScrollableClass, "space-y-3 px-1")}>
        <label className="grid gap-1.5 text-xs">
          <span>任务名称</span>
          <input className={fieldClass} value={data.name} disabled={saving} onChange={(event) => setData({ ...data, name: event.target.value })} />
          <FieldError message={errors.name} />
        </label>
        <label className="grid gap-1.5 text-xs">
          <span>执行模式</span>
          <select className={fieldClass} value={data.tier} disabled={saving} onChange={(event) => setData({ ...data, tier: event.target.value as ScheduleTaskTier })}>
            <option value="instant">直接发送</option>
            <option value="soft">AI 生成</option>
          </select>
        </label>
        <label className="grid gap-1.5 text-xs">
          <span>触发方式</span>
          <select className={fieldClass} value={data.trigger} disabled={saving} onChange={(event) => setData({ ...data, trigger: event.target.value as ScheduleTaskTrigger, when: "" })}>
            <option value="at">指定时间</option>
            <option value="after">延迟执行</option>
            <option value="every">循环执行</option>
          </select>
        </label>
        {data.trigger === "every" ? (
          <div className="grid gap-3 text-xs">
            <label className="grid gap-1.5">
              <span>周期</span>
              <select className={fieldClass} value={recurringRule.preset} disabled={saving} onChange={(event) => setRecurringRule((current) => ({ ...current, preset: event.target.value as RecurringSchedulePreset }))}>
                {recurringScheduleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            {recurringRule.preset === "weekly" ? (
              <label className="grid gap-1.5">
                <span>星期</span>
                <select className={fieldClass} value={recurringRule.weekday} disabled={saving} onChange={(event) => setRecurringRule((current) => ({ ...current, weekday: event.target.value }))}>
                  {weekdayOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            ) : null}
            {recurringRule.preset === "daily" || recurringRule.preset === "weekly" ? (
              <label className="grid gap-1.5">
                <span>执行时间</span>
                <input className={fieldClass} type="time" value={recurringRule.time} disabled={saving} onChange={(event) => setRecurringRule((current) => ({ ...current, time: event.target.value }))} />
              </label>
            ) : null}
            {recurringRule.preset === "custom" ? (
              <label className="grid gap-1.5">
                <span>自定义规则</span>
                <input className={fieldClass} type="text" placeholder={whenPlaceholder} value={recurringRule.custom} disabled={saving} onChange={(event) => setRecurringRule((current) => ({ ...current, custom: event.target.value }))} />
              </label>
            ) : null}
            <FieldError message={errors.when} />
          </div>
        ) : (
          <label className="grid gap-1.5 text-xs">
            <span>{whenLabel}</span>
            <input className={fieldClass} type={data.trigger === "at" ? "datetime-local" : "text"} placeholder={data.trigger === "at" ? undefined : whenPlaceholder} value={data.when} disabled={saving} onChange={(event) => setData({ ...data, when: event.target.value })} />
            <FieldError message={errors.when} />
          </label>
        )}
        <label className="grid gap-1.5 text-xs">
          <span>执行内容</span>
          <textarea className={`${fieldClass} min-h-24 resize-y`} value={data.content} disabled={saving} onChange={(event) => setData({ ...data, content: event.target.value })} />
          <FieldError message={errors.content} />
        </label>
        {error ? <div className="text-xs text-[#B42318]">{error}</div> : null}
      </div>
      <div className="flex justify-end border-t border-[#E1E7EF] pt-3">
        <button className={cx("rounded-md bg-[#272536] px-4 py-2 text-xs text-white shadow-[0_4px_12px_rgba(39,37,54,0.14)] transition-colors hover:bg-[#3B394D] disabled:opacity-50", focusResetClass)} type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</button>
      </div>
    </form>
  );
}
