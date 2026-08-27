/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleTask } from "../shared/types";
import {
  buildRecurringScheduleRule,
  createScheduleTaskFormData,
  parseRecurringScheduleRule,
  scheduleTaskFormDataFromTask,
  validateScheduleTaskForm,
} from "./roleTaskFormState";

describe("roleTaskFormState", () => {
  it("creates defaults without a timezone field", () => {
    assert.deepEqual(createScheduleTaskFormData(), {
      name: "",
      tier: "instant",
      trigger: "at",
      when: "",
      content: "",
    });
  });

  it("maps a scheduled task into editable values", () => {
    const task: RoleTask = {
      id: "task",
      role_id: "mira",
      kind: "schedule",
      status: "scheduled",
      label: "天气",
      detail: "查询天气",
      created_at: "",
      next_run_at: "",
      cancellable: true,
      editable: true,
      schedule: { tier: "soft", trigger: "every", when: "0 9 * * *", content: "查询天气" },
    };

    assert.deepEqual(scheduleTaskFormDataFromTask(task), { name: "天气", ...task.schedule });
  });

  it("parses and rebuilds structured daily and weekly recurrence rules", () => {
    const daily = parseRecurringScheduleRule("30 14 * * *");
    const weekly = parseRecurringScheduleRule("15 8 * * 5");

    assert.deepEqual(daily, { preset: "daily", time: "14:30", weekday: "1", custom: "" });
    assert.deepEqual(weekly, { preset: "weekly", time: "08:15", weekday: "5", custom: "" });
    assert.equal(buildRecurringScheduleRule(daily), "30 14 * * *");
    assert.equal(buildRecurringScheduleRule(weekly), "15 8 * * 5");
  });

  it("preserves custom recurrence rules", () => {
    const custom = parseRecurringScheduleRule("*/5 * * * *");

    assert.deepEqual(custom, { preset: "custom", time: "09:00", weekday: "1", custom: "*/5 * * * *" });
    assert.equal(buildRecurringScheduleRule(custom), "*/5 * * * *");
  });

  it("validates required fields but leaves schedule syntax to the backend", () => {
    const missing = validateScheduleTaskForm(createScheduleTaskFormData());
    assert.deepEqual(Object.keys(missing).sort(), ["content", "name", "when"]);
    assert.deepEqual(validateScheduleTaskForm({
      name: "提醒",
      tier: "instant",
      trigger: "every",
      when: "由后端判断",
      content: "喝水",
    }), {});
  });
});
