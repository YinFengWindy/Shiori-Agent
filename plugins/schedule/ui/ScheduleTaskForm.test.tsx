/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createFakeHostServices } from "@yinfengwindy/shiori-sdk/testing";
import type { ScheduleTaskFormData } from "./types";
import { ScheduleTaskForm } from "./ScheduleTaskForm";

function renderForm(initialData: ScheduleTaskFormData, saving = false, error = "") {
  return renderToStaticMarkup(
    <ScheduleTaskForm
      title="新增计划任务"
      initialData={initialData}
      saving={saving}
      error={error}
      host={createFakeHostServices().host}
      onBack={() => undefined}
      onSave={async () => undefined}
    />,
  );
}

describe("ScheduleTaskForm", () => {
  it("uses a date-time control for at schedules", () => {
    const markup = renderForm({
      name: "提醒",
      tier: "instant",
      trigger: "at",
      when: "2026-07-18T09:30",
      content: "喝水",
    });

    assert.match(markup, /type="datetime-local"/);
    assert.match(markup, /value="2026-07-18T09:30"/);
    assert.match(markup, /role="group" aria-label="执行模式"/);
    assert.match(markup, /role="group" aria-label="触发方式"/);
    assert.match(markup, /aria-pressed="true"[^>]*>直接发送</);
    assert.match(markup, /data-autosize-textarea-mirror=""/);
    assert.doesNotMatch(markup, /focus:ring/);
  });

  it("uses a preset dropdown for recurring schedules", () => {
    const markup = renderForm({
      name: "提醒",
      tier: "instant",
      trigger: "every",
      when: "1h",
      content: "喝水",
    });

    assert.match(markup, /role="combobox"/);
    assert.match(markup, /每小时/);
    assert.doesNotMatch(markup, /placeholder="例如 1h 或 0 9 \* \* \*"/);
  });

  it("separates daily recurrence from its execution time", () => {
    const markup = renderForm({
      name: "提醒",
      tier: "instant",
      trigger: "every",
      when: "30 14 * * *",
      content: "喝水",
    });

    assert.match(markup, />每天<\/span>/);
    assert.match(markup, />执行时间</);
    assert.match(markup, /type="time" value="14:30"/);
  });

  it("separates weekly recurrence into weekday and execution time", () => {
    const markup = renderForm({
      name: "提醒",
      tier: "instant",
      trigger: "every",
      when: "15 8 * * 5",
      content: "喝水",
    });

    assert.match(markup, />每周<\/span>/);
    assert.match(markup, />周五<\/span>/);
    assert.match(markup, /type="time" value="08:15"/);
  });

  it("keeps custom recurring rules editable", () => {
    const markup = renderForm({
      name: "提醒",
      tier: "instant",
      trigger: "every",
      when: "*/5 * * * *",
      content: "喝水",
    }, true, "保存失败");

    assert.match(markup, />自定义<\/span>/);
    assert.match(markup, /type="text"/);
    assert.match(markup, /value="\*\/5 \* \* \* \*"/);
    assert.match(markup, />保存中…</);
    assert.match(markup, />保存失败</);
    assert.match(markup, /disabled=""/);
  });
});
