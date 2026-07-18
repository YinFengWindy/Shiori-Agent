import { ArrowLeft } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";
import type { ScheduleTaskFormData, ScheduleTaskTier, ScheduleTaskTrigger } from "../shared/types";
import { cx, focusResetClass } from "../shared/styles";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import {
  buildRecurringScheduleRule,
  parseRecurringScheduleRule,
  validateScheduleTaskForm,
  type ScheduleTaskFormErrors,
} from "./roleTaskFormState";
import {
  RoleTaskFieldError,
  RoleTaskSegmentedControl,
  roleTaskFieldClass,
  roleTaskFieldLabelClass,
} from "./RoleTaskFormControls";
import { RoleTaskScheduleFields } from "./RoleTaskScheduleFields";
import {
  chatSidebarBackButtonClass,
  chatSidebarHeaderClass,
  chatSidebarPanelClass,
  chatSidebarScrollableClass,
} from "./chatSidebarStyles";

const scheduleTierOptions = [
  { value: "instant", label: "直接发送" },
  { value: "soft", label: "AI 生成" },
] as const;

const scheduleTriggerOptions = [
  { value: "at", label: "指定时间" },
  { value: "after", label: "延迟执行" },
  { value: "every", label: "循环执行" },
] as const;

const sectionHeadingClass = "text-[11px] font-semibold tracking-[0.12em] text-[#7A8593]";

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

  return (
    <form className={cx(chatSidebarPanelClass, "grid-rows-[auto_minmax(0,1fr)_auto]")} onSubmit={(event) => void submit(event)}>
      <div className={cx(chatSidebarHeaderClass, "gap-2")}>
        <button className={chatSidebarBackButtonClass} type="button" aria-label="返回" disabled={saving} onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="font-semibold text-[#272536]">{title}</span>
      </div>
      <div className={cx(chatSidebarScrollableClass, "space-y-5 px-1 pb-5")}>
        <section className="grid gap-3">
          <h3 className={sectionHeadingClass}>基础信息</h3>
          <label className={roleTaskFieldLabelClass}>
            <span>任务名称</span>
            <input className={roleTaskFieldClass} value={data.name} disabled={saving} onChange={(event) => setData((current) => ({ ...current, name: event.target.value }))} />
            <RoleTaskFieldError message={errors.name} />
          </label>
        </section>
        <section className="grid gap-3 border-t border-[#E1E7EF] pt-4">
          <h3 className={sectionHeadingClass}>执行设置</h3>
          <div className="grid gap-1.5 text-xs text-[#667085]">
            <span>执行模式</span>
            <RoleTaskSegmentedControl
              label="执行模式"
              value={data.tier}
              options={scheduleTierOptions}
              disabled={saving}
              onChange={(tier: ScheduleTaskTier) => setData((current) => ({ ...current, tier }))}
            />
          </div>
          <div className="grid gap-1.5 text-xs text-[#667085]">
            <span>触发方式</span>
            <RoleTaskSegmentedControl
              label="触发方式"
              value={data.trigger}
              options={scheduleTriggerOptions}
              disabled={saving}
              onChange={(trigger: ScheduleTaskTrigger) => setData((current) => ({ ...current, trigger, when: "" }))}
            />
          </div>
          <RoleTaskScheduleFields
            trigger={data.trigger}
            when={data.when}
            recurringRule={recurringRule}
            saving={saving}
            error={errors.when}
            onWhenChange={(when) => setData((current) => ({ ...current, when }))}
            onRecurringRuleChange={setRecurringRule}
          />
        </section>
        <section className="grid gap-3 border-t border-[#E1E7EF] pt-4">
          <h3 className={sectionHeadingClass}>任务内容</h3>
          <label className={roleTaskFieldLabelClass}>
            <span>执行内容</span>
            <AutosizeTextarea
              className={`${roleTaskFieldClass} min-h-32`}
              containerClassName="min-h-32"
              mirrorClassName="min-h-32 border border-transparent px-3 py-2.5 text-sm"
              rows={1}
              value={data.content}
              disabled={saving}
              onChange={(event) => setData((current) => ({ ...current, content: event.target.value }))}
            />
            <RoleTaskFieldError message={errors.content} />
          </label>
        </section>
        {error ? <div className="text-xs text-[#B42318]">{error}</div> : null}
      </div>
      <div className="pt-3">
        <button className={cx("flex h-10 w-full items-center justify-center rounded-md bg-[#272536] px-4 text-xs font-medium text-white shadow-[0_4px_12px_rgba(39,37,54,0.14)] transition-colors hover:bg-[#3B394D] disabled:opacity-50", focusResetClass)} type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</button>
      </div>
    </form>
  );
}
