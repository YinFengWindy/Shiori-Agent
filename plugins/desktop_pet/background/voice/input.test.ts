import assert from "node:assert/strict";
import { test } from "node:test";
import { deferred } from "@yinfengwindy/shiori-sdk/testing";
import type { NativeAudio, PluginNativeApi } from "@yinfengwindy/shiori-sdk";
import { PetVoiceInput } from "./input";

test("release then cancel while native start is pending releases capture and never transcribes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const start = deferred<void>(); let cancels = 0; let transcribed = 0;
  const audio: PluginNativeApi["audio"] = { devices: async () => [], startCapture: () => start.promise, stopCapture: async () => ({ audio_base64: "AQ==", format: "wav" }), cancelCapture: async () => { cancels++; }, play: async () => {}, stop: async () => {} };
  const input = new PetVoiceInput(audio, { enabled: () => true, device: () => "mic", status: () => {}, interrupt: () => {}, captured: async () => { transcribed++; } });
  input.press("surface"); t.mock.timers.tick(300);
  const releasing = input.release("surface"); input.cancel();
  assert.equal(cancels, 1);
  start.resolve(); await releasing;
  assert.equal(transcribed, 0);
});

test("a cancelled pending stop and failed-start timeout cannot complete a newer recording", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const stop = deferred<NativeAudio>(); let stops = 0; let captured = 0; let starts = 0;
  const audio: PluginNativeApi["audio"] = { devices: async () => [], startCapture: async () => { if (++starts === 1) throw new Error("no mic"); }, stopCapture: () => { stops++; return stop.promise; }, cancelCapture: async () => {}, play: async () => {}, stop: async () => {} };
  const input = new PetVoiceInput(audio, { enabled: () => true, device: () => "", status: () => {}, interrupt: () => {}, captured: async () => { captured++; } });
  input.press("surface"); t.mock.timers.tick(300); for (let i = 0; i < 5; i++) await Promise.resolve();
  t.mock.timers.tick(30_000); input.press("surface"); t.mock.timers.tick(300);
  t.mock.timers.tick(30_000); assert.equal(stops, 0);
  const releasing = input.release("surface"); await Promise.resolve(); input.cancel();
  stop.resolve({ audio_base64: "late", format: "wav" }); await releasing;
  assert.equal(captured, 0);
});
