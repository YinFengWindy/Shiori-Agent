import assert from "node:assert/strict";
import { test } from "node:test";
import { createDashboardStore, mergeTaskList } from "./dashboardStore";
import { herdrBackend, makeAgent, makeDetail, makeSummary, makeWorkspace } from "./testFixtures";

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

test("a list without newer revisions keeps its references; another process replaces it", () => {
  const current = { instance_id: "p", tasks: [makeSummary({ revision: 3 }), makeSummary({ id: "task-b" })] };
  assert.equal(mergeTaskList(current, { instance_id: "p", tasks: [makeSummary({ revision: 2 }), makeSummary({ id: "task-b" })] }), current);
  const advanced = mergeTaskList(current, { instance_id: "p", tasks: [makeSummary({ revision: 3 }), makeSummary({ id: "task-b", revision: 2 })] });
  assert.equal(advanced.tasks[0], current.tasks[0]);
  assert.equal(advanced.tasks[1].revision, 2);
  const fresh = { instance_id: "q", tasks: [makeSummary({ revision: 1 })] };
  assert.equal(mergeTaskList(current, fresh), fresh);
});

test("the first agent is picked; the selection stays through polls, even once its agent is gone", async () => {
  const p2 = makeAgent();
  const p4 = makeAgent({ pane_id: "wR:p4", title: "第二个" });
  const backend = herdrBackend([makeDetail()], [], [makeWorkspace("Shiori", [p2, p4])]);
  const store = createDashboardStore(5);
  const detach = store.attach(backend.client, backend.fake.host);
  await settle();
  assert.deepEqual(store.getSnapshot().selection, { kind: "agent", paneId: "wR:p2" }, "an agent is picked over a task");
  store.select({ kind: "agent", paneId: "wR:p4" });
  backend.setWorkspaces([makeWorkspace("Shiori", [makeAgent({ pane_id: "wR:p9" }), p2, p4])]);
  await settle(30);
  assert.equal(store.getSnapshot().agents.value?.workspaces[0].agents.length, 3);
  assert.deepEqual(store.getSnapshot().selection, { kind: "agent", paneId: "wR:p4" });
  backend.setWorkspaces([makeWorkspace("Shiori", [p2])]);
  await settle(30);
  assert.equal(store.getSnapshot().agents.value?.workspaces[0].agents.length, 1);
  assert.deepEqual(store.getSnapshot().selection, { kind: "agent", paneId: "wR:p4" }, "a gone agent stays selected");
  detach();
});

test("the most recently attached client drives the list", async () => {
  const page = herdrBackend([makeDetail()]);
  const sidebar = herdrBackend([makeDetail()]);
  const store = createDashboardStore();
  const detachPage = store.attach(page.client, page.fake.host);
  const detachSidebar = store.attach(sidebar.client, sidebar.fake.host);
  await settle();
  assert.deepEqual([page.handlers.size, sidebar.handlers.size], [0, 1], "one subscription for both mount points");
  detachSidebar();
  await settle();
  assert.deepEqual([page.handlers.size, sidebar.handlers.size], [1, 0]);
  detachPage();
  assert.equal(page.handlers.size, 0);
});

test("a reconnect keeps the list visible while the renewed client takes over", async () => {
  const backend = herdrBackend([makeDetail()]);
  const store = createDashboardStore();
  const detachPage = store.attach(backend.client, backend.fake.host);
  const detachSidebar = store.attach(backend.renewClient(), backend.fake.host);
  await settle();
  const loaded = store.getSnapshot().list.value;
  assert.ok(loaded);
  // The host renews both clients: every old view detaches before the new ones attach.
  detachSidebar();
  detachPage();
  assert.equal(store.getSnapshot().list.value, loaded);
  const before = backend.calls.length;
  const detachNew = store.attach(backend.renewClient(), backend.fake.host);
  await settle();
  assert.equal(backend.handlers.size, 1);
  assert.deepEqual(backend.calls.slice(before).map((call) => call.name).sort(), ["agents.list", "tasks.list"]);
  detachNew();
});
