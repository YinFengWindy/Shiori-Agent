import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakeHostServices, createFakePluginClient, deferred } from "@yinfengwindy/shiori-sdk/testing";
import type { PluginEventHandler } from "@yinfengwindy/shiori-sdk";
import { disconnectedMessage, TaskFeed, type FeedSource } from "./taskFeed";

type Value = { revision: number };

/** Keeps the newer revision, like the real list and detail sources. */
function source(read: () => Promise<Value>): FeedSource<Value> {
  return {
    read,
    merge: (current, next) => (current && current.revision >= next.revision ? current : next),
    invalidatedBy: (current, change) => !current || change.revision > current.revision,
  };
}

function transport() {
  const handlers = new Set<PluginEventHandler>();
  const client = createFakePluginClient({ events: { on: async (_name, handler) => { handlers.add(handler); return () => { handlers.delete(handler); }; } } });
  const emit = (revision: number) => { for (const handler of handlers) handler({ task_id: "t", revision }, { id: "e", type: "event", method: "tasks.changed", payload: {} }); };
  return { client, handlers, emit };
}

test("subscribes before reading, rereads once for events during a read, and ignores stale events", async () => {
  const { client, handlers, emit } = transport();
  const fake = createFakeHostServices();
  const first = deferred<Value>();
  let reads = 0;
  const feed = new TaskFeed(source(async () => {
    assert.equal(handlers.size, 1, "the invalidation subscription exists before any read");
    reads++;
    return reads === 1 ? first.promise : { revision: 3 };
  }));
  const starting = feed.start(client, fake.host);
  await Promise.resolve();
  emit(2);
  emit(3);
  first.resolve({ revision: 1 });
  await starting;
  assert.equal(reads, 2, "two events during one read coalesce into one more read");
  assert.equal(feed.getSnapshot().value?.revision, 3);
  const settled = feed.getSnapshot();
  emit(3);
  assert.equal(reads, 2, "an event that is not newer does not read");
  feed.apply({ revision: 2 });
  assert.equal(feed.getSnapshot(), settled, "an older response keeps the same snapshot");
  feed.stop();
  assert.equal(handlers.size, 0);
});

test("a bridge exit marks the feed disconnected and drops responses still in flight; stop keeps the last value", async () => {
  const { client } = transport();
  const fake = createFakeHostServices();
  let pending = deferred<Value>();
  const feed = new TaskFeed(source(() => pending.promise));
  const starting = feed.start(client, fake.host);
  pending.resolve({ revision: 1 });
  await starting;
  pending = deferred<Value>();
  const refreshing = feed.refresh();
  fake.emit({ id: "exit", type: "event", method: "bridge.exit", payload: {} });
  pending.resolve({ revision: 5 });
  await refreshing;
  assert.deepEqual(feed.getSnapshot(), { value: { revision: 1 }, error: disconnectedMessage, connected: false });
  feed.stop();
  pending = deferred<Value>();
  const restarting = feed.start(client, fake.host);
  assert.equal(feed.getSnapshot().value?.revision, 1, "a new client refreshes in place");
  pending.resolve({ revision: 6 });
  await restarting;
  assert.deepEqual(feed.getSnapshot(), { value: { revision: 6 }, error: "", connected: true });
  feed.stop();
});

test("a subscription that resolves after stop is released", async () => {
  const fake = createFakeHostServices();
  const subscribed = deferred<() => void>();
  let released = 0;
  const feed = new TaskFeed(source(async () => ({ revision: 1 })));
  const starting = feed.start(createFakePluginClient({ events: { on: () => subscribed.promise } }), fake.host);
  feed.stop();
  subscribed.resolve(() => { released++; });
  await starting;
  assert.equal(released, 1);
  assert.equal(feed.getSnapshot().value, null);
});

test("a polled source reads again only after the previous read settles, until it stops", async () => {
  const fake = createFakeHostServices();
  const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
  let pending = deferred<Value>();
  let reads = 0;
  const feed = new TaskFeed<Value>({ read: () => { reads++; return pending.promise; }, merge: (_current, next) => next, pollMs: 1 });
  const starting = feed.start(createFakePluginClient(), fake.host);
  await wait(20);
  assert.equal(reads, 1, "no read starts while one is in flight");
  pending.resolve({ revision: 1 });
  await starting;
  pending = deferred<Value>();
  await wait(20);
  assert.equal(reads, 2);
  pending.resolve({ revision: 2 });
  feed.stop();
  await wait(20);
  assert.equal(reads, 2, "stopping ends the polling");
});
