import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { TaskSidebar } from "./TaskSidebar";
import { dashboardStore, resetDashboardStoreForTests } from "./dashboardStore";
import { herdrBackend, makeDetail, makeRole } from "./testFixtures";

afterEach(() => resetDashboardStoreForTests());

function mountSidebar(backend: ReturnType<typeof herdrBackend>, onNavigate = () => {}) {
  return mountTestComponent(
    <TaskSidebar pageId="herdr" animating={false} collapsed={false} width={280} onBeginResize={() => {}} onNavigate={onNavigate} client={backend.client} host={backend.fake.host} />,
  );
}

test("tasks are grouped into 进行中 (including ones waiting for the user) and 已结束 with avatar, title and phase", async () => {
  const role = { ...makeRole("role-a", "Mira"), avatar_abs: "D:/avatars/mira.png" };
  const backend = herdrBackend([
    makeDetail({ id: "task-done", title: "已交付的任务", status: "completed", created_at: "2026-10-14T08:00:00Z" }),
    makeDetail({ id: "task-run", title: "进行中的任务", status: "running", stage: "validation", created_at: "2026-10-14T09:00:00Z" }),
    makeDetail({ id: "task-blocked", title: "等登录的任务", status: "blocked" }),
    makeDetail({ id: "task-unknown", title: "待确认的任务", status: "unknown" }),
    makeDetail({ id: "task-failed", title: "失败的任务", status: "failed" }),
  ], [role]);
  const view = await mountSidebar(backend);
  try {
    const active = view.container.querySelector('section[aria-label="进行中"]');
    const finished = view.container.querySelector('section[aria-label="已结束"]');
    assert.match(active?.textContent ?? "", /进行中的任务.*验证/);
    assert.match(finished?.textContent ?? "", /已交付的任务.*已交付/);
    assert.match(active?.textContent ?? "", /等登录的任务.*等待处理.*待确认的任务/);
    assert.match(finished?.textContent ?? "", /失败的任务/);
    assert.doesNotMatch(finished?.textContent ?? "", /等登录的任务|待确认的任务/);
    assert.equal(active?.querySelector("img")?.getAttribute("src"), "fake-asset://D:/avatars/mira.png");
    assert.equal(view.container.querySelector('[role="combobox"], select'), null, "no filters");
  } finally { await view.cleanup(); }
});

test("an empty task list shows its empty state", async () => {
  const view = await mountSidebar(herdrBackend([]));
  try {
    assert.match(view.container.textContent ?? "", /暂无任务/);
  } finally { await view.cleanup(); }
});

test("choosing a task selects it in the shared store and closes a compact drawer", async () => {
  let navigations = 0;
  const backend = herdrBackend([makeDetail(), makeDetail({ id: "task-b", title: "第二个任务" })]);
  const view = await mountSidebar(backend, () => { navigations++; });
  try {
    const second = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent?.includes("第二个任务"));
    assert.ok(second);
    await act(async () => second.click());
    assert.equal(dashboardStore.getSnapshot().selectedId, "task-b");
    assert.equal(second.getAttribute("aria-current"), "true");
    assert.equal(navigations, 1);
  } finally { await view.cleanup(); }
});
