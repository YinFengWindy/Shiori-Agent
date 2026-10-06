import assert from "node:assert/strict";
import { test } from "node:test";
import type { BackgroundCtx, NativeAudio } from "@yinfengwindy/shiori-sdk";
import { deferred } from "@yinfengwindy/shiori-sdk/testing";
import { VoicePreviewController } from "./preview";

const flush = async () => { for (let index = 0; index < 12; index++) await Promise.resolve(); };

test("play acknowledges before audio finishes and stop immediately retires the active preview", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const playback = deferred<void>(); const played: NativeAudio[] = []; let stops = 0;
  const audio: BackgroundCtx["native"]["audio"] = { devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {}, play: async (value) => { played.push(value); await playback.promise; }, stop: async () => { stops++; } };
  const preview = new VoicePreviewController({ native: { audio, keys: { validate: async () => {}, register: async () => {}, unregister: async () => {} } } });
  assert.equal(preview.play("job", "role", { audio_base64: "actual-audio", format: "wav" }).phase, "playing");
  await flush(); context.mock.timers.tick(120_000); await flush();
  assert.equal(preview.snapshot().phase, "playing");
  const before = stops; await preview.stop("job");
  assert.equal(stops, before + 1); assert.equal(preview.snapshot().phase, "idle");
  playback.resolve(); await flush(); assert.equal(preview.snapshot().phase, "idle");
  assert.deepEqual(played, [{ audio_base64: "actual-audio", format: "wav" }]);
});

test("an older editor cannot stop newer playback and superseded native startup cannot play late", async () => {
  const stop = deferred<void>(); const played: NativeAudio[] = []; let stops = 0;
  const audio: BackgroundCtx["native"]["audio"] = { devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {}, play: async (value) => { played.push(value); }, stop: async () => { if (++stops === 1) await stop.promise; } };
  const preview = new VoicePreviewController({ native: { audio, keys: { validate: async () => {}, register: async () => {}, unregister: async () => {} } } });
  preview.play("old", "old-role", { audio_base64: "old", format: "wav" });
  preview.play("next", "next-role", { audio_base64: "next", format: "mp3" });
  await flush(); const before = stops; await preview.stop("old"); assert.equal(stops, before);
  stop.resolve(); await flush();
  assert.deepEqual(played, [{ audio_base64: "next", format: "mp3" }]);
  assert.equal(preview.snapshot().id, "next");
});
