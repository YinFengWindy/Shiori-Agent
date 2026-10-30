import assert from "node:assert/strict";
import { it } from "node:test";
import { mountTestComponent, chooseSelectOption } from "@yinfengwindy/shiori-sdk/testing";
import type { RecurringScheduleRule } from "./scheduleTaskFormState";

it("ScheduleTimingFields updates the recurrence preset and weekday without losing execution time", async () => {
  const view = await mountTestComponent(null);
  const { ScheduleTimingFields } = await import("./ScheduleTimingFields");
  let rule: RecurringScheduleRule = { preset: "daily", weekday: "1", time: "09:30", custom: "" };
  const renderFields = () => <ScheduleTimingFields trigger="every" when="" recurringRule={rule} saving={false} onWhenChange={() => undefined} onRecurringRuleChange={(next) => { rule = typeof next === "function" ? next(rule) : next; }} />;
  try {
    await view.render(renderFields());
    await chooseSelectOption("循环周期", "每周");
    assert.deepEqual(rule, { preset: "weekly", weekday: "1", time: "09:30", custom: "" });
    await view.render(renderFields());
    await chooseSelectOption("星期", "周五");
    assert.equal(rule.weekday, "5");
    assert.equal(rule.time, "09:30");
  } finally { await view.cleanup(); }
});
