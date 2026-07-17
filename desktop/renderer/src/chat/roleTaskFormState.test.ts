/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleTask } from "../shared/types";
import { createScheduleTaskFormData, scheduleTaskFormDataFromTask, validateScheduleTaskForm } from "./roleTaskFormState";

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
