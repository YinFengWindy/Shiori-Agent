import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { chooseSelectOption, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { DashboardPage } from "./DashboardPage";
import { dashboardFixture, makeTask } from "./testFixtures";

test("global tasks filter independently of chat role, selection and subscriptions survive updates", async () => {
  const fixture = dashboardFixture([makeTask(), makeTask({ id: "task-b", role_id: "role-b", requirement: "第二个任务", repository: "D:/other", status: "blocked", can_continue: true })]);
  const view = await mountTestComponent(<DashboardPage pageId="herdr" activeRoleId="role-a" client={fixture.client} host={fixture.fake.host} />);
  try {
    assert.match(view.container.textContent ?? "", /2 个任务/);
    assert.equal(fixture.handlers.size, 1);
    await chooseSelectOption("按角色筛选", "role-b");
    const rows = view.container.querySelectorAll('[aria-label="任务列表"] button');
    assert.equal(rows.length, 1);
    assert.match(rows[0].textContent ?? "", /第二个任务/);
    await act(async () => rows[0].dispatchEvent(new MouseEvent("click", { bubbles: true })));
    assert.match(view.container.querySelector('[aria-label="任务详情"]')?.textContent ?? "", /第二个任务/);
    await act(async () => fixture.fake.emit({ id: "exit", type: "event", method: "bridge.exit", payload: {} }));
    assert.match(view.container.textContent ?? "", /连接已断开/);
  } finally { await view.cleanup(); }
  assert.equal(fixture.handlers.size, 0);
});

test("empty and failed first snapshots have explicit states and reconnect retries", async () => {
  const fixture = dashboardFixture([]);
  fixture.fail(true);
  const view = await mountTestComponent(<DashboardPage pageId="herdr" client={fixture.client} host={fixture.fake.host} />);
  try {
    assert.match(view.container.textContent ?? "", /offline/);
    fixture.fail(false);
    const retry = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent === "重新连接");
    assert.ok(retry);
    await act(async () => retry.click());
    assert.match(view.container.textContent ?? "", /暂无任务/);
    assert.equal(fixture.handlers.size, 1);
  } finally { await view.cleanup(); }
});

test("repository and status filters combine without issuing task mutations", async () => {
  const fixture = dashboardFixture([makeTask(), makeTask({ id: "task-b", repository: "D:/other", status: "completed", requirement: "已交付任务" }), makeTask({ id: "task-c", repository: "D:/other", status: "blocked", requirement: "待处理任务" })]);
  const view = await mountTestComponent(<DashboardPage pageId="herdr" client={fixture.client} host={fixture.fake.host} />);
  try {
    await chooseSelectOption("按仓库筛选", "D:/other");
    assert.equal(view.container.querySelectorAll('[aria-label="任务列表"] button').length, 2);
    await chooseSelectOption("按状态筛选", "已交付");
    const rows = view.container.querySelectorAll('[aria-label="任务列表"] button');
    assert.equal(rows.length, 1);
    assert.match(rows[0].textContent ?? "", /已交付任务/);
    await chooseSelectOption("按状态筛选", "执行中");
    assert.match(view.container.textContent ?? "", /没有符合筛选条件/);
    assert.ok(fixture.calls.every((call) => call.name === "tasks.snapshot"));
  } finally { await view.cleanup(); }
});
