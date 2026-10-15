import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { ContinueComposer } from "./ContinueComposer";
import { makeDetail } from "./testFixtures";
import type { TaskDetailResponse } from "./types";

const continuable = makeDetail({ status: "blocked", can_continue: true });

test("the input is disabled when the task cannot continue or the bridge is down", async () => {
  const fake = createFakeHostServices();
  const client = createFakePluginClient();
  const render = (task = continuable, connected = true) => <ContinueComposer task={task} connected={connected} client={client} host={fake.host} onApplied={() => {}} />;
  const view = await mountTestComponent(render());
  try {
    const input = () => view.container.querySelector("textarea");
    assert.equal(input()?.disabled, false);
    await view.render(render(makeDetail({ status: "running", can_continue: false })));
    assert.equal(input()?.disabled, true);
    await view.render(render(continuable, false));
    assert.equal(input()?.disabled, true);
  } finally { await view.cleanup(); }
});

test("sending submits once, applies the service's answer and clears; a failure keeps the draft", async () => {
  const fake = createFakeHostServices();
  const request = deferred<TaskDetailResponse>();
  const calls: unknown[] = [];
  const applied: TaskDetailResponse[] = [];
  let answer: () => Promise<TaskDetailResponse> = () => request.promise;
  const client = createFakePluginClient({ call: async <T,>(name: string, payload?: Record<string, unknown>) => { calls.push({ name, payload }); return await answer() as T; } });
  const view = await mountTestComponent(<ContinueComposer task={continuable} connected client={client} host={fake.host} onApplied={(response) => applied.push(response)} />);
  try {
    const input = view.container.querySelector("textarea");
    const send = view.container.querySelector<HTMLButtonElement>('button[type="submit"]');
    assert.ok(input && send);
    await changeInputValue(input, "补一条测试\n第二行");
    await act(async () => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    assert.deepEqual(calls, [{ name: "tasks.continue", payload: { task_id: "task-a", requirement: "补一条测试\n第二行" } }]);
    const response = { instance_id: "p", task: makeDetail({ status: "queued", revision: 2 }) };
    await act(async () => request.resolve(response));
    assert.deepEqual(applied, [response]);
    assert.equal(input.value, "");

    answer = () => Promise.reject(new Error("Agent 尚未就绪"));
    await changeInputValue(input, "再来一次");
    await act(async () => send.click());
    assert.match(view.container.textContent ?? "", /Agent 尚未就绪/);
    assert.equal(input.value, "再来一次");
  } finally { await view.cleanup(); }
});
