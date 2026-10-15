import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { CancelTaskButton, OpenPullRequestButton } from "./TaskActions";
import { makeDetail } from "./testFixtures";
import type { TaskDetailResponse } from "./types";

function button(container: HTMLElement, text: string) {
  const found = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent?.trim() === text);
  assert.ok(found, text);
  return found;
}

test("cancel asks first and applies the service's state, which may still be 取消中", async () => {
  const fake = createFakeHostServices();
  const calls: string[] = [];
  const applied: TaskDetailResponse[] = [];
  const response = { instance_id: "p", task: makeDetail({ status: "cancelling", can_cancel: false, revision: 2 }) };
  const client = createFakePluginClient({ call: async <T,>(name: string) => { calls.push(name); return response as T; } });
  const view = await mountTestComponent(<CancelTaskButton task={makeDetail()} connected client={client} host={fake.host} onApplied={(next) => applied.push(next)} />);
  try {
    await act(async () => button(view.container, "取消").click());
    assert.deepEqual(calls, []);
    assert.ok(view.container.querySelector('[role="dialog"]'));
    await act(async () => button(view.container, "确认取消").click());
    assert.deepEqual(calls, ["tasks.cancel"]);
    assert.deepEqual(applied, [response]);
    assert.equal(view.container.querySelector('[role="dialog"]'), null);
  } finally { await view.cleanup(); }
});

test("cancel is not offered when the service refuses it and is disabled while the bridge is down", async () => {
  const fake = createFakeHostServices();
  const client = createFakePluginClient();
  const render = (task = makeDetail(), connected = true) => <CancelTaskButton task={task} connected={connected} client={client} host={fake.host} onApplied={() => {}} />;
  const view = await mountTestComponent(render(makeDetail({ status: "completed", can_cancel: false })));
  try {
    assert.equal(view.container.querySelector("button"), null);
    await view.render(render(makeDetail({ status: "cancelled", can_cancel: false })));
    assert.equal(view.container.querySelector("button"), null);
    await view.render(render(makeDetail(), false));
    assert.equal(button(view.container, "取消").disabled, true);
  } finally { await view.cleanup(); }
});

test("opening the Draft PR goes through the host and reports a refusal", async () => {
  const fake = createFakeHostServices({ openExternal: async () => { throw new Error("blocked"); } });
  const view = await mountTestComponent(<OpenPullRequestButton url="https://github.com/o/r/pull/1" host={fake.host} />);
  try {
    await act(async () => button(view.container, "打开 Draft PR").click());
    assert.ok(fake.calls.some((call) => call.service === "openExternal" && call.url === "https://github.com/o/r/pull/1"));
    assert.equal(fake.feedback[0]?.message, "打开 Draft PR 失败");
  } finally { await view.cleanup(); }
});
