import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakePluginClient, deferred } from "@yinfengwindy/shiori-sdk/testing";
import type { BackgroundCtx, TtsResult } from "@yinfengwindy/shiori-sdk";
import { PetReplyAudio } from "./replyAudio";
import { PetSpeechQueue } from "./speechQueue";

test("manual stop drops late audio and serializes new speech behind real old inference", async () => {
  const synthesis = deferred<TtsResult>(); const calls: string[] = []; let stopped = 0;
  const audio: BackgroundCtx["native"]["audio"] = { devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {}, play: async (value) => { calls.push(`play:${value.audio_base64}`); }, stop: async () => { stopped++; } };
  const rpc = createFakePluginClient({ services: { list: async () => ({ services: [] }), call: async <T,>(_provider: unknown, _method: string, payload?: Record<string, unknown>) => { calls.push(String(payload?.text)); return (calls.length === 1 ? await synthesis.promise : { audio_base64: "new", format: "wav" }) as T; } } });
  const replies = new PetReplyAudio({ rpc }, new PetSpeechQueue(audio), () => {});
  const provider = { plugin_id: "neutral", service_id: "tts" };
  replies.begin(); replies.push("旧句。下一句。", true, provider, "role", "开心");
  await Promise.resolve(); await replies.stop();
  // Nothing was playing yet: the host's global stop would only cut another source's speech.
  assert.equal(stopped, 0);
  replies.begin(); replies.push("新句。", true, provider, "role", "平静");
  await Promise.resolve(); assert.deepEqual(calls, ["旧句。"]);
  synthesis.resolve({ audio_base64: "old", format: "mp3" });
  for (let i = 0; i < 20; i++) await Promise.resolve();
  assert.deepEqual(calls, ["旧句。", "新句。", "play:new"]);
});
