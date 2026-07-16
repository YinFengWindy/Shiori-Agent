/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { ScheduleTaskFormData } from "../shared/types";
import { RoleTaskForm } from "./RoleTaskForm";

function renderForm(initialData: ScheduleTaskFormData, saving = false, error = "") {
  return renderToStaticMarkup(
    <RoleTaskForm
      title="新增计划任务"
      initialData={initialData}
      saving={saving}
      error={error}
      onBack={() => undefined}
      onSave={async () => undefined}
    />,
  );
}

describe("RoleTaskForm", () => {
  it("uses a date-time control for at schedules", () => {
    const markup = renderForm({
      name: "提醒",
      tier: "instant",
      trigger: "at",
      when: "2026-07-18T09:30",
      content: "喝水",
      timezone: "Asia/Shanghai",
    });

    assert.match(markup, /type="datetime-local"/);
    assert.match(markup, /value="2026-07-18T09:30"/);
  });

  it("keeps interval syntax as text and exposes pending errors", () => {
    const markup = renderForm({
      name: "提醒",
      tier: "instant",
      trigger: "every",
      when: "1h",
      content: "喝水",
      timezone: "UTC",
    }, true, "保存失败");

    assert.match(markup, /type="text"/);
    assert.match(markup, />保存中…</);
    assert.match(markup, />保存失败</);
    assert.match(markup, /disabled=""/);
  });
});
