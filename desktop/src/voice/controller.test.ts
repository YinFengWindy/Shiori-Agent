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

function response(payload: Record<string, unknown> = {}): BridgeResponse {
  return { id: "id", type: "response", method: "test", payload, error: null };
}

function createController(overrides: {
  recorder?: FakeRecorder;
  invoke?: (request: { method: string; payload: Record<string, unknown> }) => Promise<BridgeResponse>;
  enabled?: boolean;
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
    now: () => clock,
    schedule: (callback, delayMs) => {
      nextTimer += 1;
      if (nextTimer === 1) {
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
      return request.method === "voice.transcribe" ? response({ text: "你好" }) : response();
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
