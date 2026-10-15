import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { AgentSidebar } from "./AgentSidebar";
import { createDashboardStore, DashboardStoreProvider } from "./dashboardStore";
import { herdrBackend, makeAgent, makeDetail, makeRole, makeWorkspace } from "./testFixtures";

function mountSidebar(backend: ReturnType<typeof herdrBackend>, onNavigate = () => {}, store = createDashboardStore()) {
  return mountTestComponent(
    <DashboardStoreProvider value={store}>
      <AgentSidebar pageId="herdr" animating={false} collapsed={false} width={280} onBeginResize={() => {}} onNavigate={onNavigate} client={backend.client} host={backend.fake.host} />
    </DashboardStoreProvider>,
  );
}

const section = (container: HTMLElement, label: string) => container.querySelector(`section[aria-label="${label}"]`)?.textContent ?? "";

test("agents are grouped by workspace; a task's agent appears once, as its task, and other tasks follow", async () => {
  const role = { ...makeRole("role-a", "Mira"), avatar_abs: "D:/avatars/mira.png" };
  const backend = herdrBackend(
    [
      makeDetail({ id: "task-run", title: "进行中的任务", status: "running", stage: "validation" }),
      makeDetail({ id: "task-done", title: "已交付的任务", status: "completed", finished: true }),
      makeDetail({ id: "task-new", title: "启动中的任务", status: "preparing", stage: "" }),
    ],
    [role],
    [
      makeWorkspace("Shiori", [makeAgent(), makeAgent({ pane_id: "wR:p4", agent: "codex", status: "blocked", title: "" })]),
      makeWorkspace("shiori-task", [makeAgent({ pane_id: "w9:p1", workspace_id: "w9", agent: "codex", task_id: "task-run" })]),
    ],
  );
  const view = await mountSidebar(backend);
  try {
    assert.match(section(view.container, "Shiori"), /herdr插件问题.*Claude Code · 工作中.*Codex.*Codex · 等待输入/);
    const taskGroup = section(view.container, "shiori-task");
    assert.match(taskGroup, /进行中的任务.*验证/);
    assert.doesNotMatch(taskGroup, /herdr插件问题/);
    assert.equal(view.container.querySelector('section[aria-label="shiori-task"] img')?.getAttribute("src"), "fake-asset://D:/avatars/mira.png");
    const others = section(view.container, "插件任务");
    assert.match(others, /启动中的任务.*已交付的任务/, "unfinished first");
    assert.doesNotMatch(others, /进行中的任务/, "a task carried by a listed agent is not listed twice");
  } finally { await view.cleanup(); }
});

test("an unavailable session still lists every plugin task", async () => {
  const backend = herdrBackend([makeDetail({ title: "已交付的任务", status: "completed", finished: true })]);
  backend.failAgents(new Error("Herdr session 'default' 未运行"));
  const view = await mountSidebar(backend);
  try {
    assert.match(section(view.container, "插件任务"), /已交付的任务/);
  } finally { await view.cleanup(); }
});

test("without agents or tasks the sidebar shows its empty state", async () => {
  const view = await mountSidebar(herdrBackend([]));
  try {
    assert.match(view.container.textContent ?? "", /暂无 Agent/);
  } finally { await view.cleanup(); }
});

test("choosing an agent selects it in the shared store and closes a compact drawer", async () => {
  let navigations = 0;
  const backend = herdrBackend([], [], [makeWorkspace("Shiori", [makeAgent(), makeAgent({ pane_id: "wR:p4", title: "第二个" })])]);
  const store = createDashboardStore();
  const view = await mountSidebar(backend, () => { navigations++; }, store);
  try {
    const second = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent?.includes("第二个"));
    assert.ok(second);
    await act(async () => second.click());
    assert.deepEqual(store.getSnapshot().selection, { kind: "agent", paneId: "wR:p4" });
    assert.equal(second.getAttribute("aria-current"), "true");
    assert.equal(navigations, 1);
  } finally { await view.cleanup(); }
});
