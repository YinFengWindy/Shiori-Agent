import assert from "node:assert/strict";
import { test } from "node:test";
import { createDashboardStore, mergeTaskList } from "./dashboardStore";
import { herdrBackend, makeDetail, makeSummary } from "./testFixtures";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("a list without newer revisions keeps its references; another process replaces it", () => {
  const current = { instance_id: "p", tasks: [makeSummary({ revision: 3 }), makeSummary({ id: "task-b" })] };
  assert.equal(mergeTaskList(current, { instance_id: "p", tasks: [makeSummary({ revision: 2 }), makeSummary({ id: "task-b" })] }), current);
  const advanced = mergeTaskList(current, { instance_id: "p", tasks: [makeSummary({ revision: 3 }), makeSummary({ id: "task-b", revision: 2 })] });
  assert.equal(advanced.tasks[0], current.tasks[0]);
  assert.equal(advanced.tasks[1].revision, 2);
  const fresh = { instance_id: "q", tasks: [makeSummary({ revision: 1 })] };
  assert.equal(mergeTaskList(current, fresh), fresh);
});

test("the selection stays through a task added later and moves to the first task once it is gone", async () => {
  const backend = herdrBackend([makeDetail(), makeDetail({ id: "task-b" })]);
  const store = createDashboardStore();
  const detach = store.attach(backend.client, backend.fake.host);
  await settle();
  assert.equal(store.getSnapshot().selectedId, "task-a", "the first loaded task is picked");
  store.select("task-b");
  backend.setTasks([makeDetail({ id: "task-new" }), makeDetail(), makeDetail({ id: "task-b" })]);
  backend.emit("task-new", 1);
  await settle();
  assert.equal(store.getSnapshot().selectedId, "task-b");
  backend.setTasks([makeDetail({ id: "task-new" }), makeDetail()]);
  backend.emit("task-b", 9);
  await settle();
  assert.equal(store.getSnapshot().selectedId, "task-new");
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
  assert.deepEqual(backend.calls.slice(before).map((call) => call.name), ["tasks.list"]);
  detachNew();
});
