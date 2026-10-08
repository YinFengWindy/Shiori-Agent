import assert from "node:assert/strict";
import { test } from "node:test";
import type { BackgroundCtx, BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient, deferred } from "@yinfengwindy/shiori-sdk/testing";
import { PetVoiceController } from "./controller";
import { PetSpeechQueue } from "./speechQueue";
import type { VoiceStatePayload } from "./types";
import { defaultVoicePreferences } from "./preferences";

const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
function fixture() {
  const states: VoiceStatePayload[] = []; const calls: string[] = []; const requests: Array<{ role_id: string; turn_id: string }> = [];
  const preferences = { ...defaultVoicePreferences, enabled: true, asr: { plugin_id: "neutral", service_id: "asr" }, tts: { plugin_id: "neutral", service_id: "tts" } };
  const ctx: Pick<BackgroundCtx, "rpc" | "native" | "chat" | "reportFailure"> = {
    rpc: createFakePluginClient({ call: async <T,>(_name: string, payload?: Record<string, unknown>) => ({ role_id: payload?.role_id, session_key: `session:${payload?.role_id}`, mood: "开心" }) as T,
      services: { list: async () => ({ services: [] }), call: async <T,>(_ref: unknown, name: string, payload?: Record<string, unknown>) => {
        calls.push(name === "synthesize" ? `tts:${payload?.text}:${payload?.mood}` : name);
        return (name === "transcribe" ? { text: "你好" } : { audio_base64: "AQ==", format: "wav" }) as T;
      } } }),
    native: { audio: { devices: async () => [], startCapture: async () => { calls.push("record"); }, stopCapture: async () => ({ audio_base64: "AQ==", format: "wav" }), cancelCapture: async () => {}, play: async () => { calls.push("play"); }, stop: async () => { calls.push("stop"); } }, keys: { validate: async () => {}, register: async () => {}, unregister: async () => {} } },
    chat: { send: async (request) => { requests.push(request); return {}; }, cancel: async ({ turn_id }) => { calls.push(`cancel:${turn_id}`); return {}; } }, reportFailure: (_operation, error) => { throw error; },
  };
  const controller = new PetVoiceController(ctx, preferences, (state) => states.push(state), new PetSpeechQueue(ctx.native.audio));
  const event = (method: string, payload: Record<string, unknown>): BridgeEvent => ({ id: "request", type: "event", method, payload });
  return { controller, ctx, states, calls, requests, preferences, event };
}

test("only the pet's exact session and turn speak; delta/error need no role_id and interruption cancels old chat", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] }); const f = fixture(); f.controller.bind("role");
  const speak = async () => { f.controller.gesture("press"); t.mock.timers.tick(300); f.controller.gesture("release"); await flush(); };
  await speak(); const old = f.requests[0].turn_id;
  f.controller.handle(f.event("chat.delta", { turn_id: old, session_key: "other", content_delta: "拒绝。" }));
  f.controller.handle(f.event("chat.delta", { turn_id: "ordinary", session_key: "session:role", content_delta: "拒绝。" }));
  f.controller.handle(f.event("chat.delta", { turn_id: old, session_key: "session:role", content_delta: "欢迎。" }));
  await flush(); assert.ok(f.calls.includes("tts:欢迎。:开心")); assert.equal(f.calls.some((call) => call.includes("拒绝")), false);
  await speak(); assert.ok(f.calls.includes(`cancel:${old}`));
  const latest = f.requests[1].turn_id;
  f.controller.handle(f.event("chat.error", { turn_id: old, session_key: "session:role", message: "old" }));
  assert.notEqual(f.states.at(-1)?.message, "old");
  f.controller.handle(f.event("chat.error", { turn_id: latest, session_key: "session:role", message: "current" }));
  assert.equal(f.states.at(-1)?.message, "current");
  await f.controller.dispose();
});

test("disabled speech, a hidden pet and a locked screen admit no recording", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] }); const f = fixture(); f.controller.bind("role");
  await f.controller.configure({ ...f.preferences, enabled: false });
  f.controller.gesture("press"); t.mock.timers.tick(500);
  await f.controller.configure(f.preferences); f.controller.bind(""); f.controller.gesture("press"); t.mock.timers.tick(500);
  f.controller.bind("role"); f.controller.setLocked(true); f.controller.gesture("press"); t.mock.timers.tick(500);
  assert.equal(f.calls.includes("record"), false);
  f.controller.setLocked(false); f.controller.gesture("press"); t.mock.timers.tick(300); f.controller.gesture("release"); await flush();
  assert.equal(f.requests.length, 1); await f.controller.dispose();
});

test("a failed send retires its turn so late server events cannot begin speech", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] }); const f = fixture(); f.controller.bind("role");
  f.ctx.chat.send = async (request) => { f.requests.push(request); throw new Error("send failed"); };
  f.controller.gesture("press"); t.mock.timers.tick(300); f.controller.gesture("release"); await flush();
  assert.equal(f.states.at(-1)?.message, "send failed");
  f.controller.handle(f.event("chat.done", { role_id: "role", turn_id: f.requests[0].turn_id, session_key: "session:role", reply: "不能播放。" }));
  await flush(); assert.equal(f.calls.some((call) => call.startsWith("tts:")), false);
  await f.controller.dispose();
});

test("disabling speech while a key registration is pending removes the late registration", async () => {
  const f = fixture(); const registration = deferred<void>(); const keys = new Set<string>();
  f.ctx.native.keys.register = async (id) => { await registration.promise; keys.add(id); };
  f.ctx.native.keys.unregister = async (id) => { keys.delete(id); };
  f.controller.bind("role"); await flush();
  const configured = f.controller.configure({ ...f.preferences, enabled: false });
  registration.resolve(); await configured;
  assert.deepEqual([...keys], []); await f.controller.dispose();
});
