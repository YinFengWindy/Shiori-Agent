import { ArrowLeft } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";
import {
  AutosizeTextarea,
  chatSidebarHeaderClass,
  chatSidebarPanelClass,
  chatSidebarScrollableClass,
  compactIconButtonClass,
  cx,
  primaryButtonSurfaceClass,
  settingsInputClass,
  type PluginHostServices,
} from "@yinfengwindy/shiori-sdk";
import type { ScheduleTaskFormData, ScheduleTier, ScheduleTrigger } from "./types";
import {
  buildRecurringScheduleRule,
  parseRecurringScheduleRule,
  scheduleTierLabels,
  scheduleTriggerLabels,
  validateScheduleTaskForm,
  type ScheduleTaskFormErrors,
} from "./scheduleTaskFormState";
import { ScheduleFieldError, ScheduleSegmentedControl, scheduleFieldLabelClass } from "./ScheduleTaskFormControls";
import { ScheduleTimingFields } from "./ScheduleTimingFields";

const scheduleTierOptions = (["instant", "soft"] as const).map((value) => ({ value, label: scheduleTierLabels[value] }));

const scheduleTriggerOptions = (["at", "after", "every"] as const).map((value) => ({ value, label: scheduleTriggerLabels[value] }));

const sectionHeadingClass = "text-[11px] font-semibold tracking-[0.12em] text-ink-muted";

/** Renders the create/edit form of a scheduled task; it fills the task panel. */
export function ScheduleTaskForm({ title, initialData, saving, error, host, onBack, onSave }: {
  title: string;
  initialData: ScheduleTaskFormData;
  saving: boolean;
  error: string;
  host: PluginHostServices;
  onBack: () => void;
  onSave: (data: ScheduleTaskFormData) => Promise<void>;
}) {
  const [data, setData] = useState(initialData);
  const [recurringRule, setRecurringRule] = useState(() => parseRecurringScheduleRule(initialData.when));
  const [errors, setErrors] = useState<ScheduleTaskFormErrors>({});
  const { InlineError } = host.ui;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const submittedData = data.trigger === "every" ? { ...data, when: buildRecurringScheduleRule(recurringRule) } : data;
    const nextErrors = validateScheduleTaskForm(submittedData);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    try {
      await onSave(submittedData);
    } catch {
      // The failure is shown through `error`.
      return;
    }
  };

  return (
    <form className={cx(chatSidebarPanelClass, "grid-rows-[auto_minmax(0,1fr)_auto]")} onSubmit={(event) => void submit(event)}>
      <div className={cx(chatSidebarHeaderClass, "gap-2")}>
        <button className={compactIconButtonClass} type="button" aria-label="返回" disabled={saving} onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="min-w-0 truncate font-semibold text-ink">{title}</span>
      </div>
      <div className={cx(chatSidebarScrollableClass, "min-w-0 space-y-5 overflow-x-hidden px-1 pb-5")}>
        <section className="grid gap-3">
          <h3 className={sectionHeadingClass}>基础信息</h3>
          <label className={scheduleFieldLabelClass}>
            <span>任务名称</span>
            <input className={settingsInputClass} value={data.name} disabled={saving} onChange={(event) => setData((current) => ({ ...current, name: event.target.value }))} />
            <ScheduleFieldError message={errors.name} />
          </label>
        </section>
        <section className="grid gap-3 border-t border-line-soft pt-4">
          <h3 className={sectionHeadingClass}>执行设置</h3>
          <div className="grid min-w-0 gap-1.5 text-xs text-ink-muted">
            <span>执行模式</span>
            <ScheduleSegmentedControl
              label="执行模式"
              value={data.tier}
              options={scheduleTierOptions}
              disabled={saving}
              onChange={(tier: ScheduleTier) => setData((current) => ({ ...current, tier }))}
            />
          </div>
          <div className="grid min-w-0 gap-1.5 text-xs text-ink-muted">
            <span>触发方式</span>
            <ScheduleSegmentedControl
              label="触发方式"
              value={data.trigger}
              options={scheduleTriggerOptions}
              disabled={saving}
              onChange={(trigger: ScheduleTrigger) => setData((current) => ({ ...current, trigger, when: "" }))}
            />
          </div>
          <ScheduleTimingFields
            trigger={data.trigger}
            when={data.when}
            recurringRule={recurringRule}
            saving={saving}
            error={errors.when}
            onWhenChange={(when) => setData((current) => ({ ...current, when }))}
            onRecurringRuleChange={setRecurringRule}
          />
        </section>
        <section className="grid gap-3 border-t border-line-soft pt-4">
          <h3 className={sectionHeadingClass}>任务内容</h3>
          <label className={scheduleFieldLabelClass}>
            <span>执行内容</span>
            <AutosizeTextarea
              className={cx(settingsInputClass, "min-h-32")}
              containerClassName="min-h-32"
              mirrorClassName="min-h-32 border border-transparent px-2.5 py-2 text-body-sm"
              rows={1}
              value={data.content}
              disabled={saving}
              onChange={(event) => setData((current) => ({ ...current, content: event.target.value }))}
            />
            <ScheduleFieldError message={errors.content} />
          </label>
        </section>
        {error ? <InlineError message={error} /> : null}
      </div>
      <div className="pt-3">
        <button className={cx(primaryButtonSurfaceClass, "flex h-10 w-full items-center justify-center px-4 text-xs font-medium")} type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</button>
      </div>
    </form>
  );
}
