import assert from "node:assert/strict";
import { test } from "node:test";
import { deferred } from "@yinfengwindy/shiori-sdk/testing";
import type { BackgroundCtx, NativeAudio } from "@yinfengwindy/shiori-sdk";
import { PetSpeechQueue } from "./speechQueue";

const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

/** A host player whose playback lasts until the test ends it or `stop()` cuts it. */
function player() {
  const log: string[] = []; let finish: (() => void) | null = null;
  const audio: BackgroundCtx["native"]["audio"] = {
    devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {},
    play: (value: NativeAudio) => { log.push(`play:${value.audio_base64}`); return new Promise<void>((resolve) => { finish = resolve; }); },
    stop: async () => { log.push("stop"); finish?.(); },
  };
  return { audio, log, end: () => { log.push("end"); finish?.(); } };
}
const clip = (name: string): NativeAudio => ({ audio_base64: name, format: "wav" });

test("jobs from different sources play strictly one after another", async () => {
  const p = player(); const queue = new PetSpeechQueue(p.audio);
  const live = queue.enqueue({ source: "live", runId: "run" }, (job) => job.play(clip("live")));
  const chat = queue.enqueue({ source: "chat" }, (job) => job.play(clip("chat")));
  await flush(); assert.deepEqual(p.log, ["play:live"]);
  p.end(); await flush(); assert.deepEqual(p.log, ["play:live", "end", "play:chat"]);
  p.end();
  assert.deepEqual(await live, { status: "succeeded" }); assert.deepEqual(await chat, { status: "succeeded" });
});

test("cancelling one source stops only its own playing and queued speech", async () => {
  const p = player(); const queue = new PetSpeechQueue(p.audio);
  const live = queue.enqueue({ source: "live", runId: "run" }, (job) => job.play(clip("live")));
  const chat = queue.enqueue({ source: "chat" }, (job) => job.play(clip("chat")));
  const nextLive = queue.enqueue({ source: "live", runId: "run" }, (job) => job.play(clip("live-2")));
  await flush();
  // Chat cancellation while live plays: no global stop, live keeps the speaker.
  await queue.cancel({ source: "chat" }); await flush();
  assert.deepEqual(p.log, ["play:live"]);
  // Live cancellation cuts its own playback and its queued follow-up.
  await queue.cancel({ source: "live" }); await flush();
  assert.deepEqual(p.log, ["play:live", "stop"]);
  assert.deepEqual([await live, await chat, await nextLive], [{ status: "cancelled" }, { status: "cancelled" }, { status: "cancelled" }]);
});

test("a run-scoped cancel spares newer runs, and a cancelled in-flight synthesis keeps its place", async () => {
  const p = player(); const queue = new PetSpeechQueue(p.audio); const synthesis = deferred<NativeAudio>();
  const old = queue.enqueue({ source: "live", runId: "old" }, async (job) => job.play(await synthesis.promise));
  const fresh = queue.enqueue({ source: "live", runId: "new" }, (job) => job.play(clip("new")));
  await flush(); await queue.cancel({ source: "live", runId: "old" });
  assert.deepEqual(p.log, [], "nothing was playing, so the host player is not stopped");
  synthesis.resolve(clip("old")); await flush();
  assert.deepEqual(p.log, ["play:new"]);
  p.end();
  assert.deepEqual([await old, await fresh], [{ status: "cancelled" }, { status: "succeeded" }]);
});

test("a failing job reports its error and the line moves on", async () => {
  const p = player(); const queue = new PetSpeechQueue(p.audio);
  const failed = queue.enqueue({ source: "live" }, async () => { throw new Error("合成失败"); });
  const next = queue.enqueue({ source: "chat" }, (job) => job.play(clip("chat")));
  assert.deepEqual(await failed, { status: "failed", error: "合成失败" });
  await flush(); p.end();
  assert.deepEqual(await next, { status: "succeeded" });
});

test("an unscoped cancel is a user stop: every source's queued and playing speech ends", async () => {
  const p = player(); const queue = new PetSpeechQueue(p.audio);
  const chat = queue.enqueue({ source: "chat" }, (job) => job.play(clip("chat")));
  const live = queue.enqueue({ source: "live", runId: "run" }, (job) => job.play(clip("live")));
  await flush(); await queue.cancel();
  assert.deepEqual(p.log, ["play:chat", "stop"]);
  assert.deepEqual([await chat, await live], [{ status: "cancelled" }, { status: "cancelled" }]);
});
