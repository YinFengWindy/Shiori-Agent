import assert from "node:assert/strict";
import test from "node:test";
import { float32ToPcm16, resampleToVoiceRate } from "./captureAudio";

test("converts clipped Float32 samples to signed PCM16", () => {
  assert.deepEqual(float32ToPcm16(new Float32Array([-1, -0.5, 0, 0.5, 1, 2])), new Int16Array([-32768, -16384, 0, 16384, 32767, 32767]));
});

test("resamples a mono chunk to 16kHz", () => {
  const result = resampleToVoiceRate(new Float32Array([0, 1, 0, -1]), 8_000);
  assert.equal(result.length, 8);
  assert.equal(result[0], 0);
  assert.equal(result[2], 1);
  assert.equal(result[4], 0);
});

test("attenuates frequencies above the 16kHz Nyquist limit when downsampling", () => {
  const alternating = Float32Array.from({ length: 480 }, (_, index) => index % 2 === 0 ? 1 : -1);
  const result = resampleToVoiceRate(alternating, 48_000);
  const peak = Math.max(...result.map((sample) => Math.abs(sample)));

  assert.ok(peak < 0.1);
});
