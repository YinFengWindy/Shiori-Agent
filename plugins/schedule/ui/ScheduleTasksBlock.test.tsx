import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { ScheduledTask } from "./types";

// Base UI binds DOM globals at import time, so the block loads inside a test window.
let ScheduleTasksBlock: typeof import("./ScheduleTasksBlock").ScheduleTasksBlock;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ ScheduleTasksBlock } = await import("./ScheduleTasksBlock"));
  await environment.cleanup();
});

function job(id: string, label: string, status: ScheduledTask["status"] = "scheduled"): ScheduledTask {
  return {
    id,
    role_id: "mira",
    status,
    label,
    detail: `${label}的内容`,
    created_at: "2026-07-11T10:00:00+00:00",
    next_run_at: "2026-07-12T01:00:00+00:00",
    editable: status === "scheduled",
    schedule: { tier: "soft", trigger: "every", when: "0 9 * * *", content: `${label}的内容` },
  };
}

/** A plugin client answering from `jobs`; `cancel` removes the job. */
function fakeBackend(jobs: ScheduledTask[]) {
  const calls: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const client = {
    async call(method: string, payload?: Record<string, unknown>) {
      calls.push({ method, payload });
      if (method === "cancel") jobs.splice(jobs.findIndex((item) => item.id === payload?.task_id), 1);
      return { tasks: [...jobs] };
    },
  } as PluginRpcClient;
  return { client, calls };
}

function buttonNamed(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll("button")).find((button) => button.textContent === text);
}

describe("ScheduleTasksBlock", () => {
  it("lists the role's jobs from its RPC and re-reads after its own event for that role", async () => {
    const jobs = [job("job-1", "喝水")];
    const { client, calls } = fakeBackend(jobs);
    const fake = createFakeHostServices();
    const view = await mountTestComponent(
      <ScheduleTasksBlock roleId="mira" view="" onViewChange={() => undefined} client={client} host={fake.host} />,
    );
    try {
      assert.match(view.container.textContent ?? "", /计划任务1喝水/);
      jobs.push(job("job-2", "天气"));
      await act(async () => fake.emit({ id: "", type: "event", method: "plugin.schedule.tasks.changed", payload: { role_id: "yin" } }));
      assert.equal(calls.length, 1);
      await act(async () => fake.emit({ id: "", type: "event", method: "plugin.schedule.tasks.changed", payload: { role_id: "mira" } }));
      assert.deepEqual(calls.map((call) => call.payload), [{ role_id: "mira" }, { role_id: "mira" }]);
      assert.match(view.container.textContent ?? "", /计划任务2喝水/);
    } finally {
      await view.cleanup();
    }
  });

  it("shows a job's schedule and cancels it after confirmation, handing the panel back", async () => {
    const { client, calls } = fakeBackend([job("job-1", "天气")]);
    const fake = createFakeHostServices();
    const views: string[] = [];
    const view = await mountTestComponent(
      <ScheduleTasksBlock roleId="mira" view="detail:job-1" onViewChange={(next) => views.push(next)} client={client} host={fake.host} />,
    );
    try {
      const text = view.container.textContent ?? "";
      assert.match(text, /AI 生成/);
      assert.match(text, /循环执行/);
      assert.match(text, /0 9 \* \* \*/);

      await act(async () => buttonNamed(view.container, "取消")?.click());
      await act(async () => buttonNamed(view.container, "确认取消")?.click());

      assert.deepEqual(calls.find((call) => call.method === "cancel")?.payload, { task_id: "job-1", role_id: "mira" });
      assert.equal(views.at(-1), "");
    } finally {
      await view.cleanup();
    }
  });

  it("keeps a running job read-only", async () => {
    const { client } = fakeBackend([job("job-1", "天气", "running")]);
    const fake = createFakeHostServices();
    const view = await mountTestComponent(
      <ScheduleTasksBlock roleId="mira" view="detail:job-1" onViewChange={() => undefined} client={client} host={fake.host} />,
    );
    try {
      assert.match(view.container.textContent ?? "", /任务运行期间不可编辑/);
      assert.equal(buttonNamed(view.container, "编辑")?.disabled, true);
    } finally {
      await view.cleanup();
    }
  });
});
