import assert from "node:assert/strict";
import test from "node:test";
import { DesktopObservationController } from "./controller.js";
import type { CapturedObservationFrame, PetObservationPayload } from "./types.js";

const frame: CapturedObservationFrame = {
  frameId: "frame-1",
  capturedAt: "2026-07-23T12:00:00Z",
  width: 1000,
  height: 800,
  scaleFactor: 1.25,
  imageBase64: "png",
};

function observationPayload(overrides: Record<string, unknown> = {}) {
  return {
    frame_id: frame.frameId,
    captured_at: frame.capturedAt,
    width: frame.width,
    height: frame.height,
    scale_factor: frame.scaleFactor,
    interface_summary: "编辑器",
    activity_key: "writing",
    targets: [],
    risks: [],
    bubble: "还差一点就完成了",
    experience_candidate: "下午一起整理报告",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

test("stopping observation immediately invalidates an in-flight model result", async () => {
  let enabled = false;
  const payloads: PetObservationPayload[] = [];
  const analyze = deferred<{ payload: Record<string, unknown>; error: null }>();
  const bridge = {
    invoke: (request: { method: string }) => request.method === "observation.analyze"
      ? analyze.promise
      : Promise.resolve({ payload: {}, error: null }),
  };
  const controller = new DesktopObservationController({
    bridge,
    pet: {
      isRunning: true,
      publishObservation: (payload) => payloads.push(payload as PetObservationPayload),
    },
    getRoleId: () => "role-a",
    getEnabled: () => enabled,
    saveEnabled: async (next) => { enabled = next; },
    captureFrame: async () => frame,
    getIdleSeconds: () => 60,
  });

  await controller.start();
  await new Promise((resolve) => setImmediate(resolve));
  await controller.stop();
  assert.equal(payloads.at(-1)?.status, "off");

  analyze.resolve({ payload: observationPayload(), error: null });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(payloads.at(-1)?.status, "off");
  assert.equal(payloads.at(-1)?.bubble, "");
});

test("settled experience keeps the role and session that observed it", async () => {
  let enabled = false;
  let roleId = "role-a";
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const controller = new DesktopObservationController({
    bridge: {
      invoke: async (request: { method: string; payload: Record<string, unknown> }) => {
        requests.push(request);
        return request.method === "observation.analyze"
          ? { payload: observationPayload(), error: null }
          : { payload: { item_id: "memory-1" }, error: null };
      },
    },
    pet: { isRunning: true, publishObservation: () => undefined },
    getRoleId: () => roleId,
    getEnabled: () => enabled,
    saveEnabled: async (next) => { enabled = next; },
    captureFrame: async () => frame,
    getIdleSeconds: () => 60,
  });

  await controller.start();
  await controller.requestObservation();
  roleId = "role-b";
  await controller.stop();

  const remember = requests.find((request) => request.method === "observation.remember");
  assert.equal(remember?.payload.role_id, "role-a");
  assert.match(String(remember?.payload.source_ref), /^desktop-observation:[0-9a-f-]{36}:0$/);
});

test("screen lock pauses and shutdown preserves persistent consent", async () => {
  let enabled = false;
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    bridge: {
      invoke: async () => ({ payload: observationPayload({ experience_candidate: "" }), error: null }),
    },
    pet: {
      isRunning: true,
      publishObservation: (payload) => payloads.push(payload as PetObservationPayload),
    },
    getRoleId: () => "role-a",
    getEnabled: () => enabled,
    saveEnabled: async (next) => { enabled = next; },
    captureFrame: async () => frame,
    getIdleSeconds: () => 60,
  });

  await controller.start();
  await controller.requestObservation();
  await controller.suspend("Windows 已锁定，屏幕观察已暂停");
  assert.equal(enabled, true);
  assert.equal(payloads.at(-1)?.status, "paused");

  await controller.resume();
  assert.equal(payloads.at(-1)?.status, "observing");
  await controller.shutdown();
  assert.equal(enabled, true);
});

test("restoring while the pet is hidden pauses without revoking persisted consent", async () => {
  let enabled = true;
  let running = false;
  let saveCount = 0;
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    bridge: { invoke: async () => ({ payload: {}, error: null }) },
    pet: {
      get isRunning() { return running; },
      publishObservation: (payload) => payloads.push(payload),
    },
    getRoleId: () => "role-a",
    getEnabled: () => enabled,
    saveEnabled: async (next) => {
      saveCount += 1;
      enabled = next;
    },
    captureFrame: async () => frame,
    getIdleSeconds: () => 60,
  });

  await controller.restore();
  assert.equal(payloads.at(-1)?.status, "paused");
  assert.equal(enabled, true);
  assert.equal(saveCount, 0);

  running = true;
  await controller.restore();
  assert.equal(payloads.at(-1)?.status, "observing");
  assert.equal(enabled, true);
  await controller.shutdown();
});

test("the model may request one fresh screenshot but no unbounded refresh loop", async () => {
  let enabled = true;
  let captureCount = 0;
  let analyzeCount = 0;
  const refreshedFrame = { ...frame, frameId: "frame-2", capturedAt: "2026-07-23T12:01:00Z" };
  const controller = new DesktopObservationController({
    bridge: {
      invoke: async (request: { method: string }) => {
        if (request.method !== "observation.analyze") return { payload: {}, error: null };
        analyzeCount += 1;
        return analyzeCount === 1
          ? { payload: { request: "screenshot" }, error: null }
          : {
              payload: observationPayload({
                frame_id: refreshedFrame.frameId,
                captured_at: refreshedFrame.capturedAt,
                experience_candidate: "",
              }),
              error: null,
            };
      },
    },
    pet: { isRunning: true, publishObservation: () => undefined },
    getRoleId: () => "role-a",
    getEnabled: () => enabled,
    saveEnabled: async (next) => { enabled = next; },
    captureFrame: async () => {
      captureCount += 1;
      return captureCount === 1 ? frame : refreshedFrame;
    },
    getIdleSeconds: () => 60,
  });

  await controller.restore();
  await controller.requestObservation();
  assert.equal(captureCount, 2);
  assert.equal(controller.state, "observing");
  await controller.shutdown();
});

test("transient bubbles expire in the controller and repeated bubbles are suppressed", async () => {
  let enabled = true;
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    bridge: {
      invoke: async () => ({
        payload: observationPayload({ experience_candidate: "" }),
        error: null,
      }),
    },
    pet: {
      isRunning: true,
      publishObservation: (payload) => payloads.push(payload),
    },
    getRoleId: () => "role-a",
    getEnabled: () => enabled,
    saveEnabled: async (next) => { enabled = next; },
    captureFrame: async () => frame,
    getIdleSeconds: () => 60,
    bubbleDurationMs: 5,
  });

  await controller.restore();
  await controller.requestObservation();
  assert.equal(payloads.at(-1)?.bubble, "还差一点就完成了");
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.equal(payloads.at(-1)?.bubble, "");

  await controller.requestObservation();
  assert.equal(payloads.at(-1)?.bubble, "");
  controller.dismissBubble();
  assert.equal(payloads.at(-1)?.bubble, "");
  await controller.shutdown();
});

test("a second toggle cancels an in-flight enable before any screenshot is captured", async () => {
  let enabled = false;
  let captureCount = 0;
  const enabling = deferred<void>();
  const controller = new DesktopObservationController({
    bridge: { invoke: async () => ({ payload: {}, error: null }) },
    pet: { isRunning: true, publishObservation: () => undefined },
    getRoleId: () => "role-a",
    getEnabled: () => enabled,
    saveEnabled: async (next) => {
      if (next) await enabling.promise;
      enabled = next;
    },
    captureFrame: async () => {
      captureCount += 1;
      return frame;
    },
    getIdleSeconds: () => 60,
  });

  const start = controller.toggle();
  await new Promise((resolve) => setImmediate(resolve));
  const stop = controller.toggle();
  enabling.resolve();
  await Promise.all([start, stop]);

  assert.equal(enabled, false);
  assert.equal(captureCount, 0);
  assert.equal(controller.state, "off");
});
