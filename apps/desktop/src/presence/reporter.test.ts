import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import type { BridgeResponse } from "../bridge/shared.js";
import {
  desktopPresencePollIntervalMs,
  desktopPresenceReportMethod,
  startDesktopPresenceReporting,
  type DesktopPresenceMonitor,
} from "./reporter.js";

class FakeMonitor extends EventEmitter implements DesktopPresenceMonitor {
  idleSeconds = 0;
  getSystemIdleTime(): number {
    return this.idleSeconds;
  }
}

class FakeBridge extends EventEmitter {
  running = true;
  requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  error: BridgeResponse["error"] = null;
  isRunning(): boolean {
    return this.running;
  }
  async invoke(request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> {
    this.requests.push(request);
    return { id: "r", type: "response", method: request.method, payload: {}, error: this.error };
  }
}

function setup() {
  const monitor = new FakeMonitor();
  const bridge = new FakeBridge();
  const failures: unknown[] = [];
  let tick: (() => void) | null = null;
  let interval = 0;
  let cleared = false;
  const reporting = startDesktopPresenceReporting({
    monitor,
    bridge,
    onReportFailed: (error) => failures.push(error),
    timers: {
      setInterval: (callback, ms) => {
        tick = callback;
        interval = ms;
        return 1;
      },
      clearInterval: () => {
        cleared = true;
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

test("polling notices idle crossing the threshold and resumed activity", async () => {
  const { monitor, bridge, poll, interval } = setup();
  assert.equal(interval(), desktopPresencePollIntervalMs);
  await poll();
  monitor.idleSeconds = 600;
  await poll();
  await poll();
  monitor.idleSeconds = 1;
  await poll();
  assert.deepEqual(presents(bridge), [false, true]);
});

test("never starts a stopped bridge and reports once it runs again", async () => {
  const { monitor, bridge, poll } = setup();
  bridge.running = false;
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
  monitor.emit("lock-screen");
  await poll();
  assert.equal(failures.length, 1);
  bridge.error = null;
  await poll();
  assert.deepEqual(presents(bridge), [false, false]);
  assert.equal(failures.length, 1);
});

test("a bridge exit makes the next poll re-send away to the fresh backend", async () => {
  const { monitor, bridge, poll } = setup();
  monitor.emit("lock-screen");
  await poll();
  bridge.emit("exit", "bridge stopped");
  await poll();
  assert.deepEqual(presents(bridge), [false, false]);
});

test("dispose stops polling and detaches every listener", async () => {
  const { monitor, bridge, reporting, flush, cleared } = setup();
  reporting.dispose();
  assert.equal(cleared(), true);
  assert.equal(monitor.listenerCount("lock-screen"), 0);
  assert.equal(monitor.listenerCount("unlock-screen"), 0);
  assert.equal(bridge.listenerCount("exit"), 0);
  monitor.emit("lock-screen");
  await flush();
  assert.deepEqual(bridge.requests, []);
});
