import assert from "node:assert/strict";
import test from "node:test";
import { encodeVoiceWav } from "./wav.js";

test("encodes the fixed 16kHz mono PCM WAV contract", () => {
  const audio = encodeVoiceWav(new Int16Array([0, 32767, -32768]));
  const view = new DataView(audio.buffer, audio.byteOffset, audio.byteLength);

  assert.equal(new TextDecoder().decode(audio.slice(0, 4)), "RIFF");
  assert.equal(new TextDecoder().decode(audio.slice(8, 12)), "WAVE");
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16_000);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getUint32(40, true), 6);
  assert.equal(view.getInt16(44, true), 0);
  assert.equal(view.getInt16(46, true), 32767);
  assert.equal(view.getInt16(48, true), -32768);
  assert.equal(view.getUint32(4, true), audio.byteLength - 8);
});

test("does not mutate the source samples", () => {
  const samples = new Int16Array([12, -34]);
  const original = samples.slice();
  encodeVoiceWav(samples);
  assert.deepEqual(samples, original);
});
