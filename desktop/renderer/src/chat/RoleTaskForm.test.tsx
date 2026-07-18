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
    });

    assert.match(markup, /type="datetime-local"/);
    assert.match(markup, /value="2026-07-18T09:30"/);
    assert.match(markup, />基础信息</);
    assert.match(markup, />执行设置</);
    assert.match(markup, />任务内容</);
    assert.match(markup, /role="group" aria-label="执行模式"/);
    assert.match(markup, /role="group" aria-label="触发方式"/);
    assert.match(markup, /aria-pressed="true"[^>]*>直接发送</);
    assert.match(markup, /class="[^"]*w-full[^"]*" type="submit"/);
    assert.match(markup, /data-autosize-textarea-mirror=""/);
    assert.match(markup, /class="[^"]*resize-none[^"]*overflow-hidden[^"]*"[^>]*>喝水<\/textarea>/);
    assert.doesNotMatch(markup, /resize-y/);
    assert.match(markup, /focus:outline-none/);
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

    assert.match(markup, /<select/);
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

    assert.match(markup, /<option value="daily" selected="">每天<\/option>/);
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

    assert.match(markup, /<option value="weekly" selected="">每周<\/option>/);
    assert.match(markup, /<option value="5" selected="">周五<\/option>/);
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

    assert.match(markup, /<option value="custom" selected="">自定义<\/option>/);
    assert.match(markup, /type="text"/);
    assert.match(markup, /value="\*\/5 \* \* \* \*"/);
    assert.match(markup, />保存中…</);
    assert.match(markup, />保存失败</);
    assert.match(markup, /disabled=""/);
  });
});
