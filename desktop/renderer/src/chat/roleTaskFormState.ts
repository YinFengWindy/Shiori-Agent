import type { RoleTask, ScheduleTaskFormData } from "../shared/types";

export type ScheduleTaskFormErrors = Partial<Record<keyof ScheduleTaskFormData, string>>;

/** Creates the initial values for a new desktop scheduled task. */
export function createScheduleTaskFormData(timezone?: string): ScheduleTaskFormData {
  return {
    name: "",
    tier: "instant",
    trigger: "at",
    when: "",
    content: "",
    timezone: timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
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
  if (!data.timezone.trim()) errors.timezone = "请输入时区";
  return errors;
}
