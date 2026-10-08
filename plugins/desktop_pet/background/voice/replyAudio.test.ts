import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakePluginClient, deferred } from "@yinfengwindy/shiori-sdk/testing";
import type { BackgroundCtx, NativeAudio, TtsResult } from "@yinfengwindy/shiori-sdk";
import { chatReplyIdleMs, PetReplyAudio } from "./replyAudio";
import { PetSpeechQueue } from "./speechQueue";

const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
const provider = { plugin_id: "neutral", service_id: "tts" };

/** A host player whose playback lasts until the test ends it or `stop()` cuts it. */
function player() {
  const calls: string[] = []; let finish: (() => void) | null = null;
  const audio: BackgroundCtx["native"]["audio"] = {
    devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {},
    play: (value: NativeAudio) => { calls.push(`play:${value.audio_base64}`); return new Promise<void>((resolve) => { finish = resolve; }); },
    stop: async () => { calls.push("stop"); finish?.(); },
  };
  return { audio, calls, end: () => { finish?.(); } };
}

test("a retired reply drops late audio and new speech waits behind the real old inference", async () => {
  const synthesis = deferred<TtsResult>(); const p = player();
  const rpc = createFakePluginClient({ services: { list: async () => ({ services: [] }), call: async <T,>(_provider: unknown, _method: string, payload?: Record<string, unknown>) => { p.calls.push(String(payload?.text)); return (p.calls.length === 1 ? await synthesis.promise : { audio_base64: "new", format: "wav" }) as T; } } });
  const speech = new PetSpeechQueue(p.audio);
  const replies = new PetReplyAudio({ rpc }, speech, () => {});
  replies.begin(); replies.push("旧句。下一句。", true, provider, "role", "开心");
  await flush(); replies.reset(); await speech.cancel({ source: "chat" });
  assert.deepEqual(p.calls, ["旧句。"], "nothing was playing, so the host player is not stopped");
  replies.begin(); replies.push("新句。", true, provider, "role", "平静");
  await flush(); assert.deepEqual(p.calls, ["旧句。"]);
  synthesis.resolve({ audio_base64: "old", format: "mp3" });
  await flush();
  assert.deepEqual(p.calls, ["旧句。", "新句。", "play:new"]);
});

test("one streamed chat reply holds the speech line, so a live job cannot speak between its sentences", async () => {
  const p = player();
  const rpc = createFakePluginClient({ services: { list: async () => ({ services: [] }), call: async <T,>(_provider: unknown, _method: string, payload?: Record<string, unknown>) => ({ audio_base64: String(payload?.text), format: "wav" }) as T } });
  const speech = new PetSpeechQueue(p.audio);
  const replies = new PetReplyAudio({ rpc }, speech, () => {});
  replies.begin(); replies.push("第一句。", false, provider, "role", "");
  await flush();
  const live = speech.enqueue({ source: "live", runId: "run" }, (job) => job.play({ audio_base64: "直播", format: "wav" }));
  p.end(); await flush();
  assert.deepEqual(p.calls, ["play:第一句。"], "the reply is still streaming, so live waits");
  replies.push("第二句。", false, provider, "role", "");
  await flush(); p.end(); await flush();
  replies.push("", true, provider, "role", "");
  await flush();
  assert.deepEqual(p.calls, ["play:第一句。", "play:第二句。", "play:直播"]);
  p.end(); assert.deepEqual(await live, { status: "succeeded" });
});

test("a reply that stops streaming releases the speech line after the idle timeout, and its later sentences re-queue behind live", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const p = player();
  const rpc = createFakePluginClient({ services: { list: async () => ({ services: [] }), call: async <T,>(_provider: unknown, _method: string, payload?: Record<string, unknown>) => ({ audio_base64: String(payload?.text), format: "wav" }) as T } });
  const speech = new PetSpeechQueue(p.audio);
  const statuses: string[] = [];
  const replies = new PetReplyAudio({ rpc }, speech, (status) => statuses.push(status));
  replies.begin(); replies.push("第一句。", false, provider, "role", "");
  await flush(); p.end(); await flush();
  const live = speech.enqueue({ source: "live", runId: "run" }, (job) => job.play({ audio_base64: "直播", format: "wav" }));
  t.mock.timers.tick(chatReplyIdleMs - 1); await flush();
  assert.deepEqual(p.calls, ["play:第一句。"]);
  t.mock.timers.tick(1); await flush();
  assert.deepEqual(p.calls, ["play:第一句。", "play:直播"], "the stalled reply no longer holds the line");
  replies.push("迟到的一句。", false, provider, "role", "");
  await flush();
  assert.deepEqual(p.calls, ["play:第一句。", "play:直播"], "the resumed reply waits for live to finish");
  p.end(); assert.deepEqual(await live, { status: "succeeded" });
  await flush();
  assert.deepEqual(p.calls, ["play:第一句。", "play:直播", "play:迟到的一句。"]);
  p.end(); replies.push("", true, provider, "role", "");
  await flush();
  assert.equal(statuses.at(-1), "idle");
});

test("after a synthesis failure the rest of the same reply is skipped and the error stays visible", async () => {
  const p = player(); let calls = 0;
  const rpc = createFakePluginClient({ services: { list: async () => ({ services: [] }), call: async <T,>(): Promise<T> => { calls += 1; throw new Error("合成失败"); } } });
  const statuses: string[] = [];
  const replies = new PetReplyAudio({ rpc }, new PetSpeechQueue(p.audio), (status) => statuses.push(status));
  replies.begin(); replies.push("第一句。", false, provider, "role", "");
  await flush();
  replies.push("第二句。", false, provider, "role", ""); replies.push("", true, provider, "role", "");
  await flush();
  assert.equal(calls, 1);
  assert.equal(statuses.at(-1), "error");
});
