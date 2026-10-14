import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { TaskDetail } from "./TaskDetail";
import { makeTask } from "./testFixtures";

function button(container: HTMLElement, text: string) { const found = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent?.trim() === text); assert.ok(found, text); return found; }

test("continue sends the selected identity once and keeps server errors in the dialog", async () => {
  const fake = createFakeHostServices();
  const request = deferred<unknown>();
  const calls: unknown[] = [];
  const client = createFakePluginClient({ call: async <T,>(name: string, payload?: Record<string, unknown>) => { calls.push({ name, payload }); return await request.promise as T; } });
  const task = makeTask({ status: "blocked", can_continue: true });
  const view = await mountTestComponent(<TaskDetail task={task} roleName="Mira" client={client} host={fake.host} connected refresh={async () => undefined} />);
  try {
    await act(async () => button(view.container, "继续任务").click());
    const input = view.container.querySelector<HTMLTextAreaElement>("textarea"); assert.ok(input);
    await changeInputValue(input, "追加要求\n完整第二行");
    await act(async () => { button(view.container, "提交追加要求").click(); button(view.container, "提交追加要求").click(); });
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0], { name: "tasks.continue", payload: { task_id: task.id, requirement: "追加要求\n完整第二行" } });
    await act(async () => request.reject(new Error("Agent 尚未就绪")));
    assert.match(view.container.querySelector('[role="dialog"]')?.textContent ?? "", /Agent 尚未就绪/);
  } finally { await view.cleanup(); }
});

test("cancel requires confirmation, stays authoritative, and PR opening uses the host capability", async () => {
  const fake = createFakeHostServices();
  const calls: string[] = [];
  const client = createFakePluginClient({ call: async <T,>(name: string) => { calls.push(name); return {} as T; } });
  const task = makeTask({ pr_url: "https://github.com/owner/repo/pull/1" });
  const view = await mountTestComponent(<TaskDetail task={task} roleName="Mira" client={client} host={fake.host} connected refresh={async () => undefined} />);
  try {
    await act(async () => button(view.container, "取消任务").click());
    assert.deepEqual(calls, []);
    await act(async () => button(view.container, "确认取消").click());
    assert.deepEqual(calls, ["tasks.cancel"]);
    assert.match(view.container.textContent ?? "", /执行中/);
    await act(async () => button(view.container, "打开 Draft PR").click());
    assert.ok(fake.calls.some((call) => call.service === "openExternal" && call.url === task.pr_url));
  } finally { await view.cleanup(); }
});

test("stage regression is visible and monitor sync time does not replace activity time", async () => {
  const fake = createFakeHostServices(); const client = createFakePluginClient();
  const render = (stage: "implementation" | "validation") => <TaskDetail task={makeTask({ stage, updated_at: "2026-10-14T12:00:00Z", progress_updated_at: "2026-10-14T10:00:00Z" })} roleName="Mira" client={client} host={fake.host} connected refresh={async () => undefined} />;
  const view = await mountTestComponent(render("validation"));
  try { assert.equal(view.container.querySelector('[aria-current="step"]')?.textContent, "验证"); await view.render(render("implementation")); assert.equal(view.container.querySelector('[aria-current="step"]')?.textContent, "实现"); }
  finally { await view.cleanup(); }
});
