import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import type { BridgeResponse } from "../bridge/shared.js";
import type { DesktopIdleState } from "./desktopPresence.js";
import {
  desktopPresencePollIntervalMs,
  desktopPresenceReportMethod,
  startDesktopPresenceReporting,
  type DesktopPresenceMonitor,
} from "./reporter.js";

class FakeMonitor extends EventEmitter implements DesktopPresenceMonitor {
  idleState: DesktopIdleState = "active";
  thresholds: number[] = [];
  getSystemIdleState(idleThreshold: number) {
    this.thresholds.push(idleThreshold);
    return this.idleState;
  }
}

class FakeBridge extends EventEmitter {
  running = true;
  requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  error: BridgeResponse["error"] = null;
  isRunning() {
    return this.running;
  }
  async invoke(request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> {
    this.requests.push(request);
    return { id: "r", type: "response", method: request.method, payload: {}, error: this.error };
  }
  /** What the real client emits once each new session passes its health check. */
  ready() {
    this.emit("event", { id: "bridge-ready", type: "event", method: "bridge.ready", payload: {} });
  }
}

function setup() {
  const monitor = new FakeMonitor();
  const bridge = new FakeBridge();
  const failures: unknown[] = [];
  let tick: (() => void) | null = null;
  let interval = 0;
  let cleared = false;
  const handle = setInterval(() => {}, 1 << 30);
  clearInterval(handle);
  const reporting = startDesktopPresenceReporting({
    monitor,
    bridge,
    onReportFailed: (error) => failures.push(error),
    timers: {
      setInterval: (callback, ms) => {
        tick = callback;
        interval = ms;
        return handle;
      },
      clearInterval: (cleaning) => {
        cleared = cleaning === handle;
      },
    },
  });
  const flush = () => new Promise<void>((resolve) => setImmediate(resolve));
  const poll = async () => {
    tick?.();
    await flush();
  };
  return { monitor, bridge, failures, reporting, flush, poll, interval: () => interval, cleared: () => cleared };
}

const presents = (bridge: FakeBridge) => bridge.requests.map((request) => request.payload.present);

test("lock and unlock events report through the bridge method", async () => {
  const { monitor, bridge, flush } = setup();
  monitor.emit("lock-screen");
  await flush();
  monitor.emit("unlock-screen");
  await flush();
  assert.deepEqual(bridge.requests, [
    { method: desktopPresenceReportMethod, payload: { present: false } },
    { method: desktopPresenceReportMethod, payload: { present: true } },
  ]);
});

test("polling reads the idle state at the fixed threshold and reports crossings", async () => {
  const { monitor, bridge, poll, interval } = setup();
  assert.equal(interval(), desktopPresencePollIntervalMs);
  await poll();
  monitor.idleState = "idle";
  await poll();
  await poll();
  monitor.idleState = "active";
  await poll();
  assert.deepEqual(presents(bridge), [false, true]);
  assert.deepEqual(new Set(monitor.thresholds), new Set([600]));
});

test("never starts a stopped bridge and reports once it runs again", async () => {
  const { monitor, bridge, poll } = setup();
  bridge.running = false;
  monitor.idleState = "locked";
  monitor.emit("lock-screen");
  await poll();
  assert.deepEqual(bridge.requests, []);
  bridge.running = true;
  await poll();
  assert.deepEqual(presents(bridge), [false]);
});

test("a backend error response is surfaced and retried", async () => {
  const { monitor, bridge, failures, poll } = setup();
  bridge.error = { code: "internal_error", message: "boom" };
  monitor.idleState = "locked";
  monitor.emit("lock-screen");
  await poll();
  assert.equal(failures.length, 1);
  bridge.error = null;
  await poll();
  assert.deepEqual(presents(bridge), [false, false]);
  assert.equal(failures.length, 1);
});

test("a graceful restart (ready without exit) re-sends away to the new backend at once", async () => {
  const { monitor, bridge, flush } = setup();
  monitor.idleState = "locked";
  monitor.emit("lock-screen");
  await flush();
  // desktop:bridge-restart stops the old session cleanly: no "exit" is emitted,
  // only the new session's bridge.ready.
  bridge.ready();
  await flush();
  assert.deepEqual(presents(bridge), [false, false]);
});

test("the first ready of an app launched while locked reports away without waiting for a poll", async () => {
  const { monitor, bridge, flush } = setup();
  monitor.idleState = "locked";
  bridge.ready();
  await flush();
  assert.deepEqual(presents(bridge), [false]);
});

test("dispose stops polling and detaches every listener", async () => {
  const { monitor, bridge, reporting, flush, cleared } = setup();
  reporting.dispose();
  assert.equal(cleared(), true);
  assert.equal(monitor.listenerCount("lock-screen"), 0);
  assert.equal(monitor.listenerCount("unlock-screen"), 0);
  assert.equal(bridge.listenerCount("event"), 0);
  monitor.emit("lock-screen");
  bridge.ready();
  await flush();
  assert.deepEqual(bridge.requests, []);
});
