import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useEffect } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { mountTestComponent } from "./testing/domTestHarness";
import { useBridgeRefreshedValue } from "./useBridgeRefreshedValue";

type Snapshot = ReturnType<typeof useBridgeRefreshedValue<string>>;

const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
const refreshEvents: ReadonlySet<string> = new Set(["session.updated"]);
const failOnExit = (event: BridgeEvent) => (event.method === "bridge.exit" ? "stopped" : null);

async function mount(load: () => Promise<string>, options: { enabled?: boolean; onError?: (error: unknown) => void } = {}) {
  const listeners = new Set<(event: BridgeEvent) => void>();
  let latest: Snapshot | null = null;
  function Probe({ enabled, source }: { enabled: boolean; source: () => Promise<string> }) {
    const snapshot = useBridgeRefreshedValue({ enabled, load: source, refreshEvents, failOn: failOnExit, onError: options.onError });
    useEffect(() => { latest = snapshot; });
    return null;
  }
  const view = await mountTestComponent(<Probe enabled={options.enabled ?? true} source={load} />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  } } });
  await flush();
  return {
    view,
    get latest() {
      assert.ok(latest);
      return latest;
    },
    async rerender(enabled: boolean, source: () => Promise<string>) {
      await view.render(<Probe enabled={enabled} source={source} />);
      await flush();
    },
    async emit(method: string) {
      await act(async () => {
        for (const listener of [...listeners]) listener({ id: "e", type: "event", method, payload: {} } as BridgeEvent);
      });
      await flush();
    },
    async focus() {
      await act(async () => { view.window.dispatchEvent(new view.window.Event("focus")); });
      await flush();
    },
  };
}

test("loads, then reloads after listed events and window focus only", async () => {
  let calls = 0;
  const probe = await mount(async () => `v${++calls}`);
  try {
    assert.equal(probe.latest.value, "v1");
    assert.equal(probe.latest.loading, false);
    await probe.emit("session.updated");
    assert.equal(probe.latest.value, "v2");
    await probe.emit("runtime.applied");
    assert.equal(calls, 2);
    await probe.focus();
    assert.equal(probe.latest.value, "v3");
  } finally {
    await probe.view.cleanup();
  }
});

test("reloads when the loader changes and ignores responses of superseded requests", async () => {
  let releaseSlow: (value: string) => void = () => undefined;
  const slow = () => new Promise<string>((resolve) => { releaseSlow = resolve; });
  const probe = await mount(slow);
  try {
    await probe.rerender(true, async () => "fresh");
    releaseSlow("stale");
    await flush();
    assert.equal(probe.latest.value, "fresh");
  } finally {
    await probe.view.cleanup();
  }
});

test("clears the value and reports a failed load", async () => {
  const errors: unknown[] = [];
  let fail = false;
  const probe = await mount(async () => {
    if (fail) throw new Error("offline");
    return "ok";
  }, { onError: (error) => errors.push(error) });
  try {
    fail = true;
    await probe.emit("session.updated");
    assert.equal(probe.latest.value, null);
    assert.equal(probe.latest.error, "offline");
    assert.equal(errors.length, 1);
  } finally {
    await probe.view.cleanup();
  }
});

test("a failing bridge event invalidates the value and in-flight loads", async () => {
  let release: (value: string) => void = () => undefined;
  let calls = 0;
  const probe = await mount(() => {
    calls += 1;
    return calls === 1 ? Promise.resolve("first") : new Promise<string>((resolve) => { release = resolve; });
  });
  try {
    await probe.emit("session.updated");
    await probe.emit("bridge.exit");
    release("late");
    await flush();
    assert.equal(probe.latest.value, null);
    assert.equal(probe.latest.error, "stopped");
    assert.equal(probe.latest.loading, false);
  } finally {
    await probe.view.cleanup();
  }
});

test("does not load while disabled", async () => {
  let calls = 0;
  const probe = await mount(async () => `v${++calls}`, { enabled: false });
  try {
    await probe.emit("session.updated");
    assert.equal(calls, 0);
    assert.equal(probe.latest.value, null);
  } finally {
    await probe.view.cleanup();
  }
});
