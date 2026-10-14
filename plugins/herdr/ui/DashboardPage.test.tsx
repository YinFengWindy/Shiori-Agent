import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, chooseSelectOption, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleRecord } from "@yinfengwindy/shiori-sdk";
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

test("prepending a task preserves the default selection, detail scroll and continuation draft", async () => {
  const current = makeTask({ status: "blocked", can_continue: true });
  const fixture = dashboardFixture([current]);
  const view = await mountTestComponent(<DashboardPage pageId="herdr" client={fixture.client} host={fixture.fake.host} />);
  try {
    const detail = view.container.querySelector<HTMLElement>('[aria-label="任务详情"]'); assert.ok(detail);
    detail.scrollTop = 125;
    const continueButton = Array.from(detail.querySelectorAll("button")).find((item) => item.textContent === "继续任务"); assert.ok(continueButton);
    await act(async () => continueButton.click());
    const draft = view.container.querySelector<HTMLTextAreaElement>("textarea"); assert.ok(draft);
    await changeInputValue(draft, "保留这份追加要求草稿");
    const added = makeTask({ id: "task-new", requirement: "后台新建的任务", created_at: "2026-10-14T11:00:00Z" });
    fixture.setSnapshot({ instance_id: "process-a", tasks: [added, current] });
    await act(async () => fixture.emit(added.id, added.revision));
    assert.equal(view.container.querySelector('[aria-label="任务详情"]'), detail);
    assert.equal(detail.scrollTop, 125);
    assert.equal(view.container.querySelector("textarea"), draft);
    assert.equal(draft.value, "保留这份追加要求草稿");
    assert.match(view.container.querySelector('[aria-pressed="true"]')?.textContent ?? "", /修复滚动位置/);
  } finally { await view.cleanup(); }
});

test("a selected task stays visible when background progress moves it outside the active filter", async () => {
  const fixture = dashboardFixture([makeTask()]);
  const view = await mountTestComponent(<DashboardPage pageId="herdr" client={fixture.client} host={fixture.fake.host} />);
  try {
    await chooseSelectOption("按状态筛选", "执行中");
    const detail = view.container.querySelector('[aria-label="任务详情"]');
    fixture.setSnapshot({ instance_id: "process-a", tasks: [makeTask({ revision: 2, status: "completed" }), makeTask({ id: "task-new", requirement: "其他进行中的任务" })] });
    await act(async () => fixture.emit("task-a", 2));
    assert.equal(view.container.querySelector('[aria-label="任务详情"]'), detail);
    assert.match(detail?.textContent ?? "", /修复滚动位置/);
    const row = view.container.querySelector<HTMLButtonElement>('[aria-label="任务列表"] button'); assert.ok(row);
    await act(async () => row.click());
    assert.match(view.container.querySelector('[aria-label="任务详情"]')?.textContent ?? "", /其他进行中的任务/);
  } finally { await view.cleanup(); }
});

test("roles.updated refreshes the renamed role in the task list, selected filter and detail", async () => {
  const role: RoleRecord = { id: "role-a", name: "Mira", description: "", system_prompt: "", runtime_config: {}, avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null, illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {}, created_at: "", updated_at: "" };
  const fixture = dashboardFixture([makeTask()], [role]);
  const view = await mountTestComponent(<DashboardPage pageId="herdr" client={fixture.client} host={fixture.fake.host} />);
  try {
    await chooseSelectOption("按角色筛选", "Mira");
    fixture.setRoles([{ ...role, name: "改名后的 Mira" }]);
    await act(async () => fixture.fake.emit({ id: "rename", type: "event", method: "roles.updated", payload: {} }));
    for (const selector of ['[aria-label="任务列表"]', '[aria-label="按角色筛选"]', '[aria-label="任务详情"]']) {
      assert.match(view.container.querySelector(selector)?.textContent ?? "", /改名后的 Mira/);
    }
    await chooseSelectOption("按角色筛选", "改名后的 Mira");
    assert.equal(view.container.querySelectorAll('[aria-label="任务列表"] button').length, 1);
  } finally { await view.cleanup(); }
});
