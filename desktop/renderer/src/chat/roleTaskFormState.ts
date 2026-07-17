import type { RoleTask, ScheduleTaskFormData } from "../shared/types";

export type ScheduleTaskFormErrors = Partial<Record<keyof ScheduleTaskFormData, string>>;

export type RecurringSchedulePreset = "15m" | "30m" | "1h" | "2h" | "daily" | "weekly" | "custom";

export type RecurringScheduleRule = {
  preset: RecurringSchedulePreset;
  time: string;
  weekday: string;
  custom: string;
};

export const recurringScheduleOptions = [
  { value: "15m", label: "每 15 分钟" },
  { value: "30m", label: "每 30 分钟" },
  { value: "1h", label: "每小时" },
  { value: "2h", label: "每 2 小时" },
  { value: "daily", label: "每天" },
  { value: "weekly", label: "每周" },
  { value: "custom", label: "自定义" },
] as const;

export const weekdayOptions = [
  { value: "1", label: "周一" },
  { value: "2", label: "周二" },
  { value: "3", label: "周三" },
  { value: "4", label: "周四" },
  { value: "5", label: "周五" },
  { value: "6", label: "周六" },
  { value: "0", label: "周日" },
] as const;

function formatCronTime(hour: string, minute: string): string {
  return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
}

/** Parses one persisted interval or cron expression into recurring form fields. */
export function parseRecurringScheduleRule(when: string): RecurringScheduleRule {
  if (["15m", "30m", "1h", "2h"].includes(when)) {
    return { preset: when as RecurringSchedulePreset, time: "09:00", weekday: "1", custom: "" };
  }
  const dailyMatch = /^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*$/.exec(when);
  if (dailyMatch) {
    return { preset: "daily", time: formatCronTime(dailyMatch[2], dailyMatch[1]), weekday: "1", custom: "" };
  }
  const weeklyMatch = /^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+([0-7])$/.exec(when);
  if (weeklyMatch) {
    return {
      preset: "weekly",
      time: formatCronTime(weeklyMatch[2], weeklyMatch[1]),
      weekday: weeklyMatch[3] === "7" ? "0" : weeklyMatch[3],
      custom: "",
    };
  }
  if (!when) {
    return { preset: "1h", time: "09:00", weekday: "1", custom: "" };
  }
  return { preset: "custom", time: "09:00", weekday: "1", custom: when };
}

/** Serializes recurring form fields into the scheduler's existing when value. */
export function buildRecurringScheduleRule(rule: RecurringScheduleRule): string {
  if (["15m", "30m", "1h", "2h"].includes(rule.preset)) return rule.preset;
  if (rule.preset === "custom") return rule.custom.trim();
  const timeMatch = /^(\d{2}):(\d{2})$/.exec(rule.time);
  if (!timeMatch) return "";
  const cronTime = `${Number(timeMatch[2])} ${Number(timeMatch[1])}`;
  return rule.preset === "daily" ? `${cronTime} * * *` : `${cronTime} * * ${rule.weekday}`;
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
  if (!data.when.trim()) errors.when = data.trigger === "every" ? "请完善循环规则" : "请输入执行时间";
  if (!data.content.trim()) errors.content = "请输入执行内容";
  return errors;
}
