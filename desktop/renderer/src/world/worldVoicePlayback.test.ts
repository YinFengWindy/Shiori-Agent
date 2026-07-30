/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  WorldVoicePlayback,
  type WorldVoiceAudio,
  type WorldVoiceCue,
  type WorldVoiceProfile,
} from "./worldVoicePlayback";

class FakeAudio implements WorldVoiceAudio {
  onended: (() => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  src = "audio";
  playCount = 0;
  pauseCount = 0;
  loadCount = 0;
  shouldRejectPlay = false;

  play(): Promise<void> {
    this.playCount += 1;
    return this.shouldRejectPlay ? Promise.reject(new Error("play failed")) : Promise.resolve();
  }

  pause(): void {
    this.pauseCount += 1;
  }

  load(): void {
    this.loadCount += 1;
  }

  finish(): void {
    this.onended?.();
  }

  fail(): void {
    this.onerror?.(new Error("audio error"));
  }
}

function profile(overrides: Partial<WorldVoiceProfile> = {}): WorldVoiceProfile {
  return { configVersion: 1, voiceId: "voice-1", speed: 1, emotion: "calm", ...overrides };
}

function cue(overrides: Partial<WorldVoiceCue> = {}): WorldVoiceCue {
  return { cueId: "cue-1", worldId: "world-1", text: "  你好   世界  ", voiceProfile: profile(), ...overrides };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

async function flush(): Promise<void> {
  await new Promise<void>((resolve) => setImmediate(resolve));
}

describe("WorldVoicePlayback", () => {
  it("serializes playback and normalizes text before synthesis", async () => {
    const calls: string[] = [];
    const audios: FakeAudio[] = [];
    const playback = new WorldVoicePlayback({
      synthesize: async (text, voice, signal) => {
        calls.push(`${text}|${voice.voiceId}|${signal.aborted}`);
        return { audioBase64: `audio-${calls.length}`, format: "mp3" };
      },
      createAudio: () => {
        const audio = new FakeAudio();
        audios.push(audio);
        return audio;
      },
    });

    const first = playback.playCue(cue());
    const second = playback.playCue(cue({ cueId: "cue-2", text: "第二句" }));
    await flush();
    assert.deepEqual(calls, ["你好 世界|voice-1|false"]);
    assert.equal(audios.length, 1);
    audios[0].finish();
    await flush();
    assert.deepEqual(calls, ["你好 世界|voice-1|false", "第二句|voice-1|false"]);
    audios[1].finish();
    assert.deepEqual(await first, { cueId: "cue-1", status: "played" });
    assert.deepEqual(await second, { cueId: "cue-2", status: "played" });
  });

  it("does not synthesize without a valid profile", async () => {
    let synthesisCount = 0;
    const playback = new WorldVoicePlayback({
      synthesize: async () => {
        synthesisCount += 1;
        return { audioBase64: "audio", format: "mp3" };
      },
      createAudio: () => new FakeAudio(),
    });

    assert.deepEqual(await playback.playCue(cue({ voiceProfile: null })), {
      cueId: "cue-1",
      status: "no_voice",
      reason: "no_voice_profile",
    });
    assert.deepEqual(await playback.playCue(cue({ voiceProfile: profile({ voiceId: "" }) })), {
      cueId: "cue-1",
      status: "no_voice",
      reason: "no_voice_profile",
    });
    assert.equal(synthesisCount, 0);
  });

  it("caches by world, voice version, normalized text, speed, and emotion", async () => {
    let synthesisCount = 0;
    const audios: FakeAudio[] = [];
    const playback = new WorldVoicePlayback({
      synthesize: async () => {
        synthesisCount += 1;
        return { audioBase64: "cached-audio", format: "mp3" };
      },
      createAudio: () => {
        const audio = new FakeAudio();
        audios.push(audio);
        return audio;
      },
    });

    const first = playback.playCue(cue());
    await flush();
    audios[0].finish();
    assert.deepEqual(await first, { cueId: "cue-1", status: "played" });
    const second = playback.playCue(cue({ cueId: "cue-2" }));
    await flush();
    audios[1].finish();
    assert.deepEqual(await second, { cueId: "cue-2", status: "played" });
    assert.equal(synthesisCount, 1);
    assert.equal(playback.cacheSize, 1);

    const changedVersion = playback.playCue(cue({ cueId: "cue-3", voiceProfile: profile({ configVersion: 2 }) }));
    await flush();
    audios[2].finish();
    await changedVersion;
    assert.equal(synthesisCount, 2);
  });

  it("pauses and resumes current audio without starting queued cues", async () => {
    const audios: FakeAudio[] = [];
    const playback = new WorldVoicePlayback({
      synthesize: async (text) => ({ audioBase64: text, format: "mp3" }),
      createAudio: () => {
        const audio = new FakeAudio();
        audios.push(audio);
        return audio;
      },
    });
    const first = playback.playCue(cue());
    const second = playback.playCue(cue({ cueId: "cue-2", text: "第二句" }));
    await flush();
    playback.pause();
    assert.equal(audios[0].pauseCount, 1);
    assert.equal(audios[0].playCount, 1);
    playback.resume();
    assert.equal(audios[0].playCount, 2);
    audios[0].finish();
    await flush();
    assert.equal(audios.length, 2);
    audios[1].finish();
    assert.equal((await first).status, "played");
    assert.equal((await second).status, "played");
  });

  it("skips active playback, aborts synthesis, and continues the queue", async () => {
    const synthesis = deferred<{ audioBase64: string; format: "mp3" }>();
    let receivedSignal: AbortSignal | undefined;
    const audios: FakeAudio[] = [];
    const playback = new WorldVoicePlayback({
      synthesize: async (_text, _profile, signal) => {
        receivedSignal = signal;
        return synthesis.promise;
      },
      createAudio: () => {
        const audio = new FakeAudio();
        audios.push(audio);
        return audio;
      },
    });
    const first = playback.playCue(cue());
    const second = playback.playCue(cue({ cueId: "cue-2" }));
    await flush();
    playback.skip();
    assert.equal(receivedSignal?.aborted, true);
    assert.equal((await first).status, "skipped");
    synthesis.resolve({ audioBase64: "late", format: "mp3" });
    await flush();
    assert.equal(audios.length, 1);
    audios[0].finish();
    assert.equal((await second).status, "played");
  });

  it("falls back on synthesis and playback errors without throwing", async () => {
    let audioNumber = 0;
    const audios: FakeAudio[] = [];
    const playback = new WorldVoicePlayback({
      synthesize: async (text) => {
        if (text === "合成失败") throw new Error("provider unavailable");
        return { audioBase64: text, format: "mp3" };
      },
      createAudio: () => {
        const audio = new FakeAudio();
        audioNumber += 1;
        audio.shouldRejectPlay = audioNumber === 1;
        audios.push(audio);
        return audio;
      },
    });

    const synthesisFailure = playback.playCue(cue({ text: "合成失败" }));
    assert.deepEqual(await synthesisFailure, { cueId: "cue-1", status: "fallback", reason: "synthesis_failed" });
    const playbackFailure = playback.playCue(cue({ cueId: "cue-2", text: "播放失败" }));
    await flush();
    assert.deepEqual(await playbackFailure, { cueId: "cue-2", status: "fallback", reason: "playback_failed" });
  });

  it("cancels active work, destroys audio, and clears cache on dispose", async () => {
    const audios: FakeAudio[] = [];
    const playback = new WorldVoicePlayback({
      synthesize: async () => ({ audioBase64: "audio", format: "mp3" }),
      createAudio: () => {
        const audio = new FakeAudio();
        audios.push(audio);
        return audio;
      },
    });
    const outcome = playback.playCue(cue());
    await flush();
    playback.dispose();
    assert.equal((await outcome).status, "cancelled");
    assert.equal(playback.cacheSize, 0);
    assert.equal(playback.isDisposed, true);
    assert.equal(audios[0].pauseCount, 1);
    assert.equal(audios[0].src, "");
    assert.equal(audios[0].loadCount, 1);
    assert.deepEqual(await playback.playCue(cue({ cueId: "late" })), { cueId: "late", status: "cancelled", reason: "aborted" });
  });
});
