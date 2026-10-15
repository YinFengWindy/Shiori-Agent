import assert from "node:assert/strict";
import { test } from "node:test";
import { DashboardStore, mergeTaskList } from "./dashboardStore";
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

test("the first loaded task is selected once; a task added later does not move the selection", async () => {
  const backend = herdrBackend([makeDetail()]);
  const store = new DashboardStore();
  const detach = store.attach(backend.client, backend.fake.host);
  await settle();
  assert.equal(store.getSnapshot().selectedId, "task-a");
  backend.setTasks([makeDetail({ id: "task-new", created_at: "2026-10-14T11:00:00Z" }), makeDetail()]);
  backend.emit("task-new", 1);
  await settle();
  assert.equal(store.getSnapshot().list.value?.tasks[0].id, "task-new");
  assert.equal(store.getSnapshot().selectedId, "task-a");
  detach();
});

test("when the mount point driving the feed leaves, the remaining one's client takes over", async () => {
  const page = herdrBackend([makeDetail()]);
  const sidebar = herdrBackend([makeDetail()]);
  const store = new DashboardStore();
  const detachPage = store.attach(page.client, page.fake.host);
  const detachSidebar = store.attach(sidebar.client, sidebar.fake.host);
  await settle();
  assert.equal(page.handlers.size, 1);
  assert.equal(sidebar.handlers.size, 0, "one subscription for both mount points");
  detachPage();
  await settle();
  assert.equal(page.handlers.size, 0);
  assert.equal(sidebar.handlers.size, 1);
  assert.ok(sidebar.calls.some((call) => call.name === "tasks.list"));
  detachSidebar();
  assert.equal(sidebar.handlers.size, 0);
});
