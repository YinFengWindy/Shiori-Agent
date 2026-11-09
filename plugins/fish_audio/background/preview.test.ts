import assert from "node:assert/strict";
import { test } from "node:test";
import type { BackgroundCtx, NativeAudio } from "@yinfengwindy/shiori-sdk";
import { deferred } from "@yinfengwindy/shiori-sdk/testing";
import { PreviewPlayer } from "./preview";
const flush = async () => { for (let index = 0; index < 12; index++) await Promise.resolve(); };

test("an old editor cannot stop a newer preview and old startup never plays late", async () => {
  const stopped = deferred<void>();
  const played: NativeAudio[] = [];
  let stops = 0;
  const audio: BackgroundCtx["native"]["audio"] = {
    devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {},
    play: async (value) => { played.push(value); },
    stop: async () => { if (++stops === 1) await stopped.promise; },
  };
  const player = new PreviewPlayer(audio);
  player.play("old", { audio_base64: "old", format: "mp3" });
  player.play("new", { audio_base64: "new", format: "mp3" });
  await flush();
  const count = stops;
  await player.stop("old");
  assert.equal(stops, count);
  stopped.resolve(); await flush();
  assert.deepEqual(played, [{ audio_base64: "new", format: "mp3" }]);
  assert.equal(player.snapshot().id, "new");
  await player.stop("new");
  assert.equal(stops, count + 1, "an explicit user stop still reaches native audio");
  await player.dispose();
  assert.throws(() => player.play("retired", { audio_base64: "late", format: "mp3" }));
});

test("unload after capability admission closes retires pending audio without a new native call", async () => {
  const stopped = deferred<void>(); const played: NativeAudio[] = [];
  let stops = 0;
  let admissionClosed = false;
  const audio: BackgroundCtx["native"]["audio"] = {
    devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {},
    play: async (value) => { played.push(value); },
    stop: async () => {
      stops++;
      if (admissionClosed) throw new Error("background scope disposed");
      await stopped.promise;
    },
  };
  const player = new PreviewPlayer(audio);
  player.play("old", { audio_base64: "old", format: "mp3" });
  admissionClosed = true;
  await player.dispose();
  stopped.resolve(); await flush();
  assert.equal(stops, 1, "cleanup relies on the host's native-resource release");
  assert.deepEqual(played, []);
  assert.equal(player.snapshot().phase, "idle");
});
