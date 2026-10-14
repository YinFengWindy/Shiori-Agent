import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakeHostServices, createFakePluginClient, deferred } from "@yinfengwindy/shiori-sdk/testing";
import { DashboardStore } from "./dashboardStore";
import { dashboardFixture, makeTask } from "./testFixtures";
import type { TaskSnapshot } from "./types";

test("unchanged, duplicate and old snapshots retain references; current runs replace old ones", async () => {
  const fixture = dashboardFixture();
  const store = new DashboardStore(fixture.client, fixture.fake.host);
  try {
    await store.start();
    const initial = store.getSnapshot();
    await store.refresh();
    assert.equal(store.getSnapshot(), initial);
    fixture.emit("task-a", 1);
    assert.equal(fixture.calls.length, 2);
    fixture.setSnapshot({ instance_id: "process-a", tasks: [makeTask({ revision: 3, run_id: "new-run", stage: "validation" })] });
    await store.refresh();
    fixture.setSnapshot({ instance_id: "process-a", tasks: [makeTask({ revision: 2, run_id: "old-run", stage: "implementation" })] });
    await store.refresh();
    assert.equal(store.getSnapshot().tasks[0].run_id, "new-run");
    assert.equal(store.getSnapshot().tasks[0].stage, "validation");
  } finally { store.stop(); }
  assert.equal(fixture.handlers.size, 0);
});

test("subscription precedes snapshot and an event during a read schedules another authoritative read", async () => {
  const fixture = dashboardFixture();
  const first = deferred<TaskSnapshot>();
  let reads = 0;
  const client = createFakePluginClient({ events: fixture.client.events, call: async <T,>() => {
    assert.equal(fixture.handlers.size, 1);
    reads++;
    return (reads === 1 ? await first.promise : { instance_id: "p", tasks: [makeTask({ revision: 2, stage: "validation" })] }) as T;
  } });
  const store = new DashboardStore(client, fixture.fake.host);
  try {
    const starting = store.start();
    await Promise.resolve();
    fixture.emit("task-a", 2);
    first.resolve({ instance_id: "p", tasks: [makeTask()] });
    await starting;
    assert.equal(reads, 2);
    assert.equal(store.getSnapshot().tasks[0].revision, 2);
  } finally { store.stop(); }
});

test("disconnect keeps readable tasks and reconnect/new mount refreshes; late subscriptions are disposed", async () => {
  const fixture = dashboardFixture();
  const store = new DashboardStore(fixture.client, fixture.fake.host);
  await store.start();
  fixture.fail(true);
  await store.refresh();
  assert.equal(store.getSnapshot().connected, false);
  assert.equal(store.getSnapshot().tasks.length, 1);
  store.stop();
  fixture.fail(false);
  fixture.setSnapshot({ instance_id: "p2", tasks: [] });
  await store.start();
  assert.equal(store.getSnapshot().tasks.length, 0);
  store.stop();
  const pending = deferred<() => void>();
  let disposed = 0;
  const late = new DashboardStore(createFakePluginClient({ events: { on: () => pending.promise } }), createFakeHostServices().host);
  const starting = late.start();
  late.stop();
  pending.resolve(() => { disposed++; });
  await starting;
  assert.equal(disposed, 1);
});

test("a response from before disconnect cannot mark the lost connection healthy", async () => {
  const fixture = dashboardFixture();
  const pending = deferred<TaskSnapshot>();
  const client = createFakePluginClient({ events: fixture.client.events, call: async <T,>() => await pending.promise as T });
  const store = new DashboardStore(client, fixture.fake.host);
  const starting = store.start();
  await Promise.resolve();
  fixture.fake.emit({ id: "exit", type: "event", method: "bridge.exit", payload: {} });
  pending.resolve({ instance_id: "old", tasks: [makeTask()] });
  await starting;
  assert.equal(store.getSnapshot().connected, false);
  assert.equal(store.getSnapshot().tasks.length, 0);
  store.stop();
});
