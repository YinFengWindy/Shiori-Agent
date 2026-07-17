import { ArrowLeft } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";
import type { ScheduleTaskFormData, ScheduleTaskTier, ScheduleTaskTrigger } from "../shared/types";
import { cx, focusResetClass } from "../shared/styles";
import {
  customScheduleRuleValue,
  getRecurringSchedulePreset,
  recurringScheduleOptions,
  validateScheduleTaskForm,
  type ScheduleTaskFormErrors,
} from "./roleTaskFormState";

const fieldClass = cx("w-full rounded-md border border-[#D8DFE7] bg-white px-3 py-2 text-sm transition disabled:opacity-60", focusResetClass);

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
  const [errors, setErrors] = useState<ScheduleTaskFormErrors>({});

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors = validateScheduleTaskForm(data);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    try {
      await onSave(data);
    } catch {
      return;
    }
  };

  const whenLabel = data.trigger === "at" ? "执行时间" : data.trigger === "after" ? "延迟时长" : "循环规则";
  const whenPlaceholder = data.trigger === "after" ? "例如 30m、2h" : "例如 1h 或 0 9 * * *";
  const recurringPreset = data.trigger === "every" ? getRecurringSchedulePreset(data.when) : customScheduleRuleValue;

  return (
    <form className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] rounded-[20px] bg-[#F1F5F9] p-4 text-sm text-[#334155]" onSubmit={(event) => void submit(event)}>
      <div className="flex items-center gap-2 pb-3">
        <button className={cx("grid h-8 w-8 place-items-center rounded-md transition hover:bg-white", focusResetClass)} type="button" aria-label="返回" disabled={saving} onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="font-semibold text-[#272536]">{title}</span>
      </div>
      <div className="min-h-0 space-y-4 overflow-y-auto rounded-[16px] bg-white/90 p-4">
        <label className="grid gap-1 text-xs">
          <span>任务名称</span>
          <input className={fieldClass} value={data.name} disabled={saving} onChange={(event) => setData({ ...data, name: event.target.value })} />
          <FieldError message={errors.name} />
        </label>
        <label className="grid gap-1 text-xs">
          <span>执行模式</span>
          <select className={fieldClass} value={data.tier} disabled={saving} onChange={(event) => setData({ ...data, tier: event.target.value as ScheduleTaskTier })}>
            <option value="instant">直接发送</option>
            <option value="soft">AI 生成</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          <span>触发方式</span>
          <select className={fieldClass} value={data.trigger} disabled={saving} onChange={(event) => setData({ ...data, trigger: event.target.value as ScheduleTaskTrigger, when: "" })}>
            <option value="at">指定时间</option>
            <option value="after">延迟执行</option>
            <option value="every">循环执行</option>
          </select>
        </label>
        {data.trigger === "every" ? (
          <label className="grid gap-1 text-xs">
            <span>{whenLabel}</span>
            <select
              className={fieldClass}
              value={recurringPreset}
              disabled={saving}
              onChange={(event) => {
                const nextValue = event.target.value;
                setData({ ...data, when: nextValue === customScheduleRuleValue ? (recurringPreset === customScheduleRuleValue ? data.when : "") : nextValue });
              }}
            >
              {recurringScheduleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              <option value={customScheduleRuleValue}>自定义</option>
            </select>
            {recurringPreset === customScheduleRuleValue ? (
              <>
                <input className={fieldClass} type="text" placeholder={whenPlaceholder} value={data.when} disabled={saving} onChange={(event) => setData({ ...data, when: event.target.value })} />
                <FieldError message={errors.when} />
              </>
            ) : null}
          </label>
        ) : (
          <label className="grid gap-1 text-xs">
            <span>{whenLabel}</span>
            <input className={fieldClass} type={data.trigger === "at" ? "datetime-local" : "text"} placeholder={data.trigger === "at" ? undefined : whenPlaceholder} value={data.when} disabled={saving} onChange={(event) => setData({ ...data, when: event.target.value })} />
            <FieldError message={errors.when} />
          </label>
        )}
        <label className="grid gap-1 text-xs">
          <span>执行内容</span>
          <textarea className={`${fieldClass} min-h-24 resize-y`} value={data.content} disabled={saving} onChange={(event) => setData({ ...data, content: event.target.value })} />
          <FieldError message={errors.content} />
        </label>
        {error ? <div className="text-xs text-[#B42318]">{error}</div> : null}
      </div>
      <div className="flex justify-end pt-3">
        <button className={cx("rounded-md bg-[#272536] px-4 py-2 text-xs text-white transition hover:bg-[#3B394D] disabled:opacity-50", focusResetClass)} type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</button>
      </div>
    </form>
  );
}
