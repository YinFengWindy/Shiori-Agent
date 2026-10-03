import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useEffect } from "react";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
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

test("a predicate with keepValueOnError keeps the last value on failure and skips focus when asked", async () => {
  const pending: Array<{ resolve: (value: string) => void; reject: (error: Error) => void }> = [];
  const load = () => new Promise<string>((resolve, reject) => { pending.push({ resolve, reject }); });
  const refreshOn = (event: BridgeEvent) => event.method === "items.updated";
  const listeners = new Set<(event: BridgeEvent) => void>();
  function View() {
    const { value, error } = useBridgeRefreshedValue({ load, refreshEvents: refreshOn, refreshOnFocus: false, keepValueOnError: true });
    return <span>{`${value ?? "none"}|${error}`}</span>;
  }
  const view = await mountTestComponent(<View />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  } } });
  const emit = (method: string) => act(async () => {
    for (const listener of [...listeners]) listener({ id: "e", type: "event", method, payload: {} } as BridgeEvent);
  });
  try {
    await act(async () => pending[0].resolve("first"));
    await emit("items.updated");
    await emit("other");
    await act(async () => { view.window.dispatchEvent(new view.window.Event("focus")); });
    assert.equal(pending.length, 2);
    await act(async () => pending[1].reject(new Error("offline")));
    assert.equal(view.container.textContent, "first|offline");
    // The error stays while the next reload is in flight.
    await emit("items.updated");
    assert.equal(view.container.textContent, "first|offline");
    await act(async () => pending[2].resolve("second"));
    assert.equal(view.container.textContent, "second|");
  } finally { await view.cleanup(); }
});

test("read-only consumers retain a structured bridge cause for their shared error disclosure", async () => {
  const { BridgeError } = await import("@yinfengwindy/shiori-sdk");
  const probe = await mount(async () => { throw new BridgeError("本地服务处理失败", "internal_error", { detail: "phone history unavailable token=private-value" }); });
  try {
    assert.equal(probe.latest.error.split("\n")[0], "本地服务处理失败");
    assert.match(probe.latest.error, /phone history unavailable/);
    assert.doesNotMatch(probe.latest.error, /private-value/);
  } finally { await probe.view.cleanup(); }
});
