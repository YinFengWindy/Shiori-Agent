import assert from "node:assert/strict";
import { test } from "node:test";
import { PluginNativeSessions, type NativeSessionOptions } from "./sessions";

function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }
const context = { plugin_id: "demo", owner: "owner", generation: "one" };
function fixture() {
  const calls: string[] = [];
  const options: NativeSessionOptions = {
    isBackground: (sender) => sender === 7,
    authorize: async (value) => { if (value.generation !== "one") throw new Error("stale"); return value; },
    recorder: { start: async () => { calls.push("start"); }, stop: async () => new Uint8Array([1]), cancel: async () => { calls.push("cancel"); }, listInputDevices: async () => [], dispose: () => { calls.push("capture-dispose"); } },
    player: { play: async () => { calls.push("play"); }, stop: () => { calls.push("stop"); }, dispose: () => { calls.push("player-dispose"); } },
    keys: { register: () => { calls.push("key"); }, release: (token) => { calls.push(`release:${token}`); } }, keyEvent: () => {},
  };
  return { options, calls, sessions: new PluginNativeSessions(options) };
}

test("native resources reject forged windows, inactive generations and cross-owner cancellation", async () => {
  const f = fixture();
  await assert.rejects(f.sessions.open(1, context), /仅供插件后台/);
  await assert.rejects(f.sessions.open(7, { ...context, generation: "old" }), /stale/);
  const owner = await f.sessions.open(7, context);
  await assert.rejects(f.sessions.call(7, owner, "keys.validate", { accelerator: "not-a-key" }), /快捷键/);
  await f.sessions.call(7, owner, "keys.validate", { accelerator: "Ctrl+F1" });
  const stranger = await f.sessions.open(7, { ...context, plugin_id: "other", owner: "other" });
  await f.sessions.call(7, owner, "audio.start");
  await assert.rejects(f.sessions.call(1, owner, "audio.capture.cancel"), /所有者/);
  await assert.rejects(f.sessions.call(7, stranger, "audio.capture.cancel"), /其他插件/);
  const playing = deferred<void>(); f.options.player.play = () => playing.promise;
  const task = f.sessions.call(7, owner, "audio.play", { audio_base64: "AQ==", format: "wav" });
  await Promise.resolve(); await Promise.resolve();
  await assert.rejects(f.sessions.call(7, stranger, "audio.stop"), /其他插件/);
  f.options.authorize = async () => { throw new Error("backend offline"); };
  await f.sessions.call(7, owner, "audio.stop");
  await f.sessions.call(7, owner, "audio.capture.cancel");
  assert.ok(f.calls.includes("stop")); assert.ok(f.calls.includes("cancel"));
  playing.resolve(); await task;
});

test("revocation rejects a late start and old close cannot release the successor", async () => {
  const f = fixture(); const start = deferred<void>();
  f.options.recorder.start = () => start.promise;
  const old = await f.sessions.open(7, context);
  const pending = f.sessions.call(7, old, "audio.start");
  const rejected = assert.rejects(pending, /取消/);
  await Promise.resolve(); await Promise.resolve();
  f.sessions.revoke("demo");
  f.options.recorder.start = async () => {};
  const next = await f.sessions.open(7, { ...context, owner: "new" });
  await f.sessions.call(7, next, "audio.start");
  const before = f.calls.length;
  await f.sessions.call(7, old, "close");
  assert.equal(f.calls.length, before);
  start.resolve(); await rejected;
  await f.sessions.call(7, next, "audio.capture.stop");
});

test("a late stopped recording never clears or returns audio for a new operation", async () => {
  const f = fixture(); const stop = deferred<Uint8Array>(); f.options.recorder.stop = () => stop.promise;
  const token = await f.sessions.open(7, context);
  await f.sessions.call(7, token, "audio.start");
  const stopping = f.sessions.call(7, token, "audio.capture.stop"); const rejected = assert.rejects(stopping, /取消/);
  await f.sessions.call(7, token, "audio.capture.cancel");
  await f.sessions.call(7, token, "audio.start");
  stop.resolve(new Uint8Array([1])); await rejected;
  await assert.rejects(f.sessions.call(7, token, "audio.start"), /占用/);
  f.sessions.revoke();
  await assert.rejects(f.sessions.call(7, token, "audio.devices"), /所有者/);
});

test("stop revokes acquisitions still waiting for backend authorization", async () => {
  const f = fixture(); const token = await f.sessions.open(7, context); const pending = deferred<typeof context>();
  f.options.authorize = () => pending.promise;
  const start = f.sessions.call(7, token, "audio.start"); const playback = f.sessions.call(7, token, "audio.play", { audio_base64: "AQ==", format: "wav" });
  const rejectedStart = assert.rejects(start, /取消/); const rejectedPlayback = assert.rejects(playback, /取消/);
  await f.sessions.call(7, token, "audio.capture.cancel"); await f.sessions.call(7, token, "audio.stop");
  pending.resolve(context); await Promise.all([rejectedStart, rejectedPlayback]);
  assert.equal(f.calls.includes("start"), false); assert.equal(f.calls.includes("play"), false);
});
