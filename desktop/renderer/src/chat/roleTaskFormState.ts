import type { RoleTask, ScheduleTaskFormData } from "../shared/types";

export type ScheduleTaskFormErrors = Partial<Record<keyof ScheduleTaskFormData, string>>;

export const customScheduleRuleValue = "__custom__";

export const recurringScheduleOptions = [
  { value: "15m", label: "每 15 分钟" },
  { value: "30m", label: "每 30 分钟" },
  { value: "1h", label: "每小时" },
  { value: "2h", label: "每 2 小时" },
  { value: "0 9 * * *", label: "每天 09:00" },
  { value: "0 9 * * 1", label: "每周一 09:00" },
] as const;

/** Returns the matching preset value or the custom sentinel for one recurring rule. */
export function getRecurringSchedulePreset(when: string): string {
  return recurringScheduleOptions.some((option) => option.value === when) ? when : customScheduleRuleValue;
}

/** Creates the initial values for a new desktop scheduled task. */
export function createScheduleTaskFormData(): ScheduleTaskFormData {
  return {
    name: "",
    tier: "instant",
    trigger: "at",
    when: "",
    content: "",
  };
}

/** Creates editable form values from one scheduled task read model. */
export function scheduleTaskFormDataFromTask(task: RoleTask): ScheduleTaskFormData {
  if (task.kind !== "schedule" || !task.schedule) {
    throw new Error("只有计划任务可以编辑");
  }
  return { name: task.label, ...task.schedule };
}

/** Validates renderer-owned required fields without duplicating scheduler syntax rules. */
export function validateScheduleTaskForm(data: ScheduleTaskFormData): ScheduleTaskFormErrors {
  const errors: ScheduleTaskFormErrors = {};
  if (!data.name.trim()) errors.name = "请输入任务名称";
  if (!data.when.trim()) errors.when = "请输入执行时间";
  if (!data.content.trim()) errors.content = "请输入执行内容";
  return errors;
}
