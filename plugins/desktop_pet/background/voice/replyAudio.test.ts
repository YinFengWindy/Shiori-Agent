import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakePluginClient, deferred } from "@yinfengwindy/shiori-sdk/testing";
import type { BackgroundCtx, NativeAudio, TtsResult } from "@yinfengwindy/shiori-sdk";
import { PetReplyAudio } from "./replyAudio";
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
