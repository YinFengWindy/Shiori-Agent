import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { DashboardPage } from "./DashboardPage";
import { AgentSidebar } from "./AgentSidebar";
import { createDashboardStore, DashboardStoreProvider } from "./dashboardStore";
import { herdrBackend, makeDetail, makeRole } from "./testFixtures";

type Backend = ReturnType<typeof herdrBackend>;

/** Page and sidebar as the host mounts them: siblings, each with its own client, sharing one store. */
function workspace(backend: Backend, store: ReturnType<typeof createDashboardStore>, clients = { page: backend.client, sidebar: backend.client }) {
  return (
    <DashboardStoreProvider value={store}>
      <AgentSidebar pageId="herdr" animating={false} collapsed={false} width={280} onBeginResize={() => {}} client={clients.sidebar} host={backend.fake.host} />
      <DashboardPage pageId="herdr" client={clients.page} host={backend.fake.host} />
    </DashboardStoreProvider>
  );
}

function detailTitle(container: HTMLElement) {
  return container.querySelector('[aria-label="任务详情"] h1')?.textContent;
}

test("the sidebar selection drives the page; a background task does not move it", async () => {
  const backend = herdrBackend([makeDetail(), makeDetail({ id: "task-b", title: "第二个任务", role_id: "role-b" })], [makeRole("role-b", "Rin")]);
  const view = await mountTestComponent(workspace(backend, createDashboardStore()));
  try {
    assert.equal(detailTitle(view.container), "修复滚动位置");
    const second = Array.from(view.container.querySelectorAll("nav button")).find((button) => button.textContent?.includes("第二个任务"));
    assert.ok(second instanceof HTMLElement);
    await act(async () => second.click());
    assert.equal(detailTitle(view.container), "第二个任务");
    assert.match(view.container.querySelector('[aria-label="任务详情"]')?.textContent ?? "", /Rin · Codex · repo\/codex\/task/);
    backend.setTasks([makeDetail({ id: "task-new", title: "后台新任务", created_at: "2026-10-14T12:00:00Z" }), ...[makeDetail(), makeDetail({ id: "task-b", title: "第二个任务", role_id: "role-b" })]]);
    await act(async () => backend.emit("task-new", 1));
    assert.match(view.container.querySelector("nav")?.textContent ?? "", /后台新任务/);
    assert.equal(detailTitle(view.container), "第二个任务");
  } finally { await view.cleanup(); }
  assert.equal(backend.handlers.size, 0, "leaving the page releases every subscription");
});

test("without agents or tasks the page shows its empty state", async () => {
  const view = await mountTestComponent(workspace(herdrBackend([]), createDashboardStore()));
  try {
    assert.match(view.container.querySelector('[data-testid="herdr-page"]')?.textContent ?? "", /暂无 Agent/);
  } finally { await view.cleanup(); }
});

test("a lost connection shows the host error and disables the input; a renewed client refreshes", async () => {
  const backend = herdrBackend([makeDetail({ status: "blocked", can_continue: true })]);
  const store = createDashboardStore();
  const view = await mountTestComponent(workspace(backend, store));
  try {
    const input = () => view.container.querySelector<HTMLTextAreaElement>('textarea[aria-label="追加要求"]');
    assert.equal(input()?.disabled, false);
    await act(async () => backend.fake.emit({ id: "exit", type: "event", method: "bridge.exit", payload: {} }));
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /连接已断开/);
    assert.equal(input()?.disabled, true);
    // The host hands every mount point a new client once the bridge is back.
    backend.setTasks([makeDetail({ status: "blocked", can_continue: true, title: "恢复后的标题", revision: 2 })]);
    await view.render(workspace(backend, store, { page: backend.renewClient(), sidebar: backend.renewClient() }));
    assert.equal(view.container.querySelector('[role="alert"]'), null);
    assert.equal(detailTitle(view.container), "恢复后的标题");
    assert.equal(input()?.disabled, false);
  } finally { await view.cleanup(); }
});

test("task errors and report failures appear as host inline errors", async () => {
  const backend = herdrBackend([makeDetail({ status: "blocked", error: "Agent 等待登录", report_error: "渠道离线" })]);
  const view = await mountTestComponent(workspace(backend, createDashboardStore()));
  try {
    const titles = backend.fake.uiRenders.InlineError.map((props) => props.title);
    assert.ok(titles.includes("任务需要处理") && titles.includes("聊天回报失败"));
    assert.match(view.container.textContent ?? "", /Agent 等待登录[\s\S]*渠道离线/);
  } finally { await view.cleanup(); }
});

test("an unavailable session shows Herdr's reason", async () => {
  const backend = herdrBackend([]);
  backend.failAgents(new Error("Herdr session 'default' 未运行，请先启动指定 session。"));
  const view = await mountTestComponent(workspace(backend, createDashboardStore()));
  try {
    const failure = backend.fake.uiRenders.InlineError.find((props) => props.title === "Herdr session 不可用");
    assert.match(String(failure?.message), /未运行/);
  } finally { await view.cleanup(); }
});
