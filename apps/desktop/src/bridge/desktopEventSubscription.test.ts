import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import type { BridgeEvent } from "@shiori/sdk/contract";
import { PreloadLocalAssetCache } from "../assets/preloadLocalAssetCache";
import { createDesktopEventSubscription } from "./desktopEventSubscription";

function setup() {
  const ipc = new EventEmitter();
  const localAssets = new PreloadLocalAssetCache();
  const subscribe = createDesktopEventSubscription(ipc, localAssets);
  const emit = (id = "event-1") => ipc.emit("desktop:event", {}, {
    value: { id, type: "event", method: "bridge.ready", payload: {} }, assets: [],
  });
  return { ipc, localAssets, subscribe, emit };
}

test("subscriptions attach on demand and fully release across repeated lifecycles", () => {
  const { ipc, subscribe, emit } = setup();
  let calls = 0;
  assert.equal(ipc.listenerCount("desktop:event"), 0);
  for (let round = 0; round < 12; round += 1) {
    const releases = Array.from({ length: 32 }, () => subscribe(() => { calls += 1; }));
    assert.equal(ipc.listenerCount("desktop:event"), 1);
    emit();
    assert.equal(calls, (round + 1) * 32);
    releases.forEach((release) => release());
    assert.equal(ipc.listenerCount("desktop:event"), 0);
    assert.equal(emit(), false);
    assert.equal(calls, (round + 1) * 32);
  }
});

test("the same callback can be subscribed and idempotently released independently", () => {
  const { ipc, subscribe, emit } = setup();
  let calls = 0;
  const listener = () => { calls += 1; };
  const first = subscribe(listener);
  const second = subscribe(listener);
  emit();
  assert.equal(calls, 2);
  first();
  first();
  emit();
  assert.equal(calls, 3);
  assert.equal(ipc.listenerCount("desktop:event"), 1);
  second();
  assert.equal(ipc.listenerCount("desktop:event"), 0);

  const third = subscribe(listener);
  second();
  emit();
  assert.equal(calls, 4);
  assert.equal(ipc.listenerCount("desktop:event"), 1);
  third();
  assert.equal(ipc.listenerCount("desktop:event"), 0);
});

test("dispatch snapshots preserve registration order and defer subscription changes", () => {
  const { subscribe, emit } = setup();
  const calls: string[] = [];
  let releaseSecond = () => {};
  const first = subscribe((event) => {
    calls.push(`first:${event.id}`);
    if (event.id === "first-event") {
      releaseSecond();
      subscribe((next) => calls.push(`late:${next.id}`));
    }
  });
  releaseSecond = subscribe((event) => calls.push(`second:${event.id}`));

  emit("first-event");
  assert.deepEqual(calls, ["first:first-event", "second:first-event"]);
  emit("second-event");
  assert.deepEqual(calls, [
    "first:first-event", "second:first-event", "first:second-event", "late:second-event",
  ]);
  first();
});

test("a callback may release the final subscription and subscribe again during dispatch", () => {
  const { ipc, subscribe, emit } = setup();
  const calls: string[] = [];
  let release = () => {};
  release = subscribe(() => {
    calls.push("first");
    release();
    release = subscribe(() => calls.push("replacement"));
  });

  emit();
  assert.deepEqual(calls, ["first"]);
  assert.equal(ipc.listenerCount("desktop:event"), 1);
  emit();
  assert.deepEqual(calls, ["first", "replacement"]);
  release();
  assert.equal(ipc.listenerCount("desktop:event"), 0);
});

test("nested events get their own ordered dispatch and asset consumption", (t) => {
  const { localAssets, subscribe, emit } = setup();
  const consume = t.mock.method(localAssets, "consume");
  const calls: string[] = [];
  subscribe((event) => {
    calls.push(`first:${event.id}`);
    if (event.id === "outer") emit("inner");
  });
  subscribe((event) => calls.push(`second:${event.id}`));

  emit("outer");
  assert.deepEqual(calls, ["first:outer", "first:inner", "second:inner", "second:outer"]);
  assert.equal(consume.mock.callCount(), 2);
});

test("listener failures propagate and stop the current dispatch without dropping subscriptions", () => {
  const { subscribe, emit } = setup();
  const failure = new Error("subscriber failed");
  const calls: BridgeEvent[] = [];
  const release = subscribe(() => { throw failure; });
  subscribe((event) => calls.push(event));

  assert.throws(() => emit(), (error) => error === failure);
  assert.equal(calls.length, 0);
  release();
  emit();
  assert.equal(calls.length, 1);
});

test("asset consumption failures propagate before notifying any subscriber", (t) => {
  const { localAssets, subscribe, emit } = setup();
  const failure = new Error("invalid asset transport");
  t.mock.method(localAssets, "consume", () => { throw failure; });
  let calls = 0;
  subscribe(() => { calls += 1; });

  assert.throws(() => emit(), (error) => error === failure);
  assert.equal(calls, 0);
});
