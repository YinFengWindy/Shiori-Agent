import assert from "node:assert/strict";
import test from "node:test";
import type { BridgeResponse, VoiceStatePayload } from "../shared.js";
import { DesktopVoiceController, type VoiceRecorder } from "./controller.js";

class FakeRecorder implements VoiceRecorder {
  readonly calls: string[] = [];
  audio = new Uint8Array([1, 2, 3]);
  startPromise: Promise<void> = Promise.resolve();

  start(): Promise<void> {
    this.calls.push("start");
    return this.startPromise;
  }

  async stop(): Promise<Uint8Array> {
    this.calls.push("stop");
    return this.audio;
  }

  async cancel(): Promise<void> {
    this.calls.push("cancel");
  }
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function response(payload: Record<string, unknown> = {}): BridgeResponse {
  return { id: "id", type: "response", method: "test", payload, error: null };
}

function createController(overrides: {
  recorder?: FakeRecorder;
  invoke?: (request: { method: string; payload: Record<string, unknown> }) => Promise<BridgeResponse>;
  enabled?: boolean;
  runScheduleImmediately?: boolean;
} = {}) {
  const recorder = overrides.recorder ?? new FakeRecorder();
  const events: VoiceStatePayload[] = [];
  let nextTimer = 0;
  let clock = 1_000;
  const controller = new DesktopVoiceController({
    recorder,
    bridge: { invoke: overrides.invoke ?? (async () => response({ text: "你好" })) },
    isEnabled: () => overrides.enabled ?? true,
    roleId: () => "role-a",
    publishState: (payload) => events.push(payload),
    createTurnId: () => "voice-turn-1",
    now: () => clock,
    schedule: (callback, delayMs) => {
      nextTimer += 1;
      const runImmediately = overrides.runScheduleImmediately === undefined
        ? nextTimer === 1
        : overrides.runScheduleImmediately;
      if (runImmediately) {
        clock += delayMs;
        callback();
      }
      return nextTimer as unknown as ReturnType<typeof setTimeout>;
    },
    clearSchedule: () => undefined,
  });
  return { controller, recorder, events };
}

test("submits one ASR result through the existing chat.send method", async () => {
  const requests: { method: string; payload: Record<string, unknown> }[] = [];
  const { controller, recorder, events } = createController({
    invoke: async (request) => {
      requests.push(request);
      return request.method === "voice.transcribe" ? response({
        text: "你好",
        metrics: {
          provider: "tencent",
          request_id: "asr-request-1",
          elapsed_ms: 120,
          audio_duration_ms: 1000,
          character_count: 2,
          error_code: "",
        },
      }) : response();
    },
  });

  assert.equal(controller.startPress("hotkey"), true);
  controller.release();
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(recorder.calls, ["start", "stop"]);
  assert.equal(requests.length, 2);
  assert.equal(requests[0]?.method, "voice.transcribe");
  assert.equal(requests[1]?.method, "chat.send");
  assert.equal(requests[1]?.payload.input_method, "voice");
  assert.equal(requests[1]?.payload.voice_turn_id, "voice-turn-1");
  assert.deepEqual(requests[1]?.payload.asr_metrics, {
    provider: "tencent",
    request_id: "asr-request-1",
    elapsed_ms: 120,
    audio_duration_ms: 1000,
    character_count: 2,
    error_code: "",
  });
  assert.equal(events.at(-1)?.status, "waiting_reply");
});

test("does not call ASR after Esc cancellation or a disabled pet", async () => {
  const requests: string[] = [];
  const recorder = new FakeRecorder();
  const { controller } = createController({
    recorder,
    enabled: false,
    invoke: async (request) => {
      requests.push(request.method);
      return response({ text: "never" });
    },
  });
  assert.equal(controller.startPress("pet"), false);
  assert.deepEqual(recorder.calls, []);
  assert.deepEqual(requests, []);
});

test("provider errors stop before chat.send", async () => {
  const requests: string[] = [];
  const { controller, events } = createController({
    invoke: async (request) => {
      requests.push(request.method);
      return {
        ...response(),
        error: { code: "provider_error", message: "ASR 失败" },
      };
    },
  });
  controller.startPress("hotkey");
  controller.release();
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(requests, ["voice.transcribe"]);
  assert.deepEqual(events.at(-1), { status: "error", message: "ASR 失败" });
});

test("a recorder startup failure is surfaced without contacting ASR", async () => {
  const recorder = new FakeRecorder();
  recorder.startPromise = Promise.reject(new Error("权限被拒绝"));
  const requests: string[] = [];
  const { controller, events } = createController({
    recorder,
    invoke: async (request) => {
      requests.push(request.method);
      return response();
    },
  });
  controller.startPress("pet");
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(requests, []);
  assert.deepEqual(events.at(-1), { status: "error", message: "权限被拒绝" });
});

test("a new press can start while the previous sentence is speaking", async () => {
  const turnChanges: Array<[string | null, string]> = [];
  let schedules = 0;
  let turnSequence = 0;
  const active = new DesktopVoiceController({
    recorder: new FakeRecorder(),
    bridge: { invoke: async () => response({ text: "ok" }) },
    isEnabled: () => true,
    roleId: () => "mira",
    publishState: () => undefined,
    onNewInput: (previous, next) => { turnChanges.push([previous, next]); },
    createTurnId: () => `turn-${turnSequence += 1}`,
    schedule: (callback) => {
      schedules += 1;
      if (schedules === 1 || schedules === 3) callback();
      return schedules as unknown as ReturnType<typeof setTimeout>;
    },
    clearSchedule: () => undefined,
  });
  assert.equal(active.startPress("pet", 0), true);
  active.release();
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(active.currentState.kind, "waiting_reply");
  active.replyStarted(true);
  active.sentenceReady("sentence-1");

  assert.equal(active.startPress("hotkey", 10), true);
  await Promise.resolve();
  assert.deepEqual(turnChanges, [[null, "turn-1"], ["turn-1", "turn-2"]]);
  assert.equal(active.currentState.kind, "recording");
  active.cancel();
});

test("a short click or drag does not retire the active voice turn", async () => {
  const turnChanges: Array<[string | null, string]> = [];
  const scheduled: Array<() => void> = [];
  let turnSequence = 0;
  const active = new DesktopVoiceController({
    recorder: new FakeRecorder(),
    bridge: { invoke: async () => response({ text: "ok" }) },
    isEnabled: () => true,
    roleId: () => "mira",
    publishState: () => undefined,
    onNewInput: (previous, next) => { turnChanges.push([previous, next]); },
    createTurnId: () => `turn-${turnSequence += 1}`,
    schedule: (callback) => {
      scheduled.push(callback);
      return scheduled.length as unknown as ReturnType<typeof setTimeout>;
    },
    clearSchedule: () => undefined,
  });

  assert.equal(active.startPress("pet", 0), true);
  scheduled.shift()?.();
  await Promise.resolve();
  active.release();
  await new Promise<void>((resolve) => setImmediate(resolve));
  active.replyStarted(true);
  active.sentenceReady("sentence-1");
  assert.equal(active.currentState.kind, "speaking");
  assert.deepEqual(turnChanges, [[null, "turn-1"]]);

  assert.equal(active.startPress("pet", 10), true);
  active.release();
  assert.equal(active.currentState.kind, "speaking");
  assert.deepEqual(turnChanges, [[null, "turn-1"]]);

  assert.equal(active.startPress("pet", 20), true);
  active.pointerMoved();
  scheduled.forEach((callback) => callback());
  await Promise.resolve();

  assert.equal(active.currentState.kind, "speaking");
  assert.deepEqual(turnChanges, [[null, "turn-1"]]);
});

test("cancelling after release retires a recorder start that is still pending", async () => {
  const pendingStart = deferred<void>();
  const recorder = new FakeRecorder();
  recorder.startPromise = pendingStart.promise;
  const requests: string[] = [];
  const { controller, events } = createController({
    recorder,
    invoke: async (request) => {
      requests.push(request.method);
      return response({ text: "不应发送" });
    },
  });

  controller.startPress("hotkey");
  controller.release("hotkey");
  controller.cancel();
  pendingStart.resolve();
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(recorder.calls, ["start", "cancel"]);
  assert.deepEqual(requests, []);
  assert.equal(controller.currentTurnId, null);
  assert.equal(events.at(-1)?.status, "idle");
});

test("a startup failure after release remains the reported error", async () => {
  const pendingStart = deferred<void>();
  const recorder = new FakeRecorder();
  recorder.startPromise = pendingStart.promise;
  const { controller, events } = createController({ recorder });

  controller.startPress("pet");
  controller.release("pet");
  pendingStart.reject(new Error("权限被拒绝"));
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(recorder.calls, ["start"]);
  assert.deepEqual(events.at(-1), { status: "error", message: "权限被拒绝" });
});

test("a cancelled ASR result cannot send a message for a later turn", async () => {
  const asr = deferred<BridgeResponse>();
  const requests: string[] = [];
  const { controller } = createController({
    invoke: async (request) => {
      requests.push(request.method);
      if (request.method === "voice.transcribe") return await asr.promise;
      return response();
    },
  });

  controller.startPress("hotkey");
  controller.release("hotkey");
  await new Promise<void>((resolve) => setImmediate(resolve));
  controller.cancel();
  asr.resolve(response({ text: "旧转写" }));
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(requests, ["voice.transcribe"]);
  assert.equal(controller.currentState.kind, "idle");
});

test("cancelling an active reply retires its backend and playback turn", async () => {
  const cancelled: string[] = [];
  const recorder = new FakeRecorder();
  let schedules = 0;
  const controller = new DesktopVoiceController({
    recorder,
    bridge: { invoke: async () => response({ text: "你好" }) },
    isEnabled: () => true,
    roleId: () => "role-a",
    publishState: () => undefined,
    createTurnId: () => "turn-a",
    now: () => 300,
    onCancelTurn: (turnId) => cancelled.push(turnId),
    schedule: (callback) => {
      schedules += 1;
      if (schedules === 1) callback();
      return schedules as unknown as ReturnType<typeof setTimeout>;
    },
    clearSchedule: () => undefined,
  });

  controller.startPress("hotkey", 0);
  controller.release("hotkey");
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(controller.currentState.kind, "waiting_reply");

  controller.cancel();

  assert.deepEqual(cancelled, ["turn-a"]);
  assert.equal(controller.currentTurnId, null);
  assert.equal(controller.currentState.kind, "idle");
});

test("pet follow-up events cannot mutate a hotkey-owned gesture", () => {
  const { controller, recorder } = createController({ runScheduleImmediately: false });

  assert.equal(controller.startPress("hotkey", 0), true);
  controller.release("pet");
  controller.cancel("pet");

  assert.equal(controller.currentState.kind, "press_pending");
  assert.deepEqual(recorder.calls, []);
});

test("releasing a pet drag returns the controller to idle", () => {
  const { controller } = createController({ runScheduleImmediately: false });

  assert.equal(controller.startPress("pet", 0), true);
  controller.pointerMoved();
  assert.deepEqual(controller.currentState, { kind: "dragging" });

  controller.release();

  assert.deepEqual(controller.currentState, { kind: "idle" });
});

test("waits for queued playback to drain before reporting a terminal TTS failure", async () => {
  const { controller, events } = createController();
  controller.startPress("hotkey");
  controller.release();
  await new Promise<void>((resolve) => setImmediate(resolve));
  controller.replyStarted(true);
  controller.sentenceReady("sentence-1");

  controller.ttsFailed("合成服务不可用");

  assert.deepEqual(controller.currentState, { kind: "speaking", sentenceId: "sentence-1" });
  assert.equal(events.at(-1)?.status, "speaking");

  controller.replyFinished();

  assert.deepEqual(controller.currentState, { kind: "idle" });
  assert.deepEqual(events.at(-1), { status: "error", message: "合成服务不可用" });
});
