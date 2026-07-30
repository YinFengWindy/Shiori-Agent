/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PresentationCue } from "./presentationProtocol";
import { WorldAudioMixer, type WorldAudioElement } from "./worldAudioMixer";

class FakeAudio implements WorldAudioElement {
  currentTime = 0;
  loop = false;
  volume = 0;
  onended: (() => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  playCount = 0;
  pauseCount = 0;
  src = "";

  play(): void { this.playCount += 1; }
  pause(): void { this.pauseCount += 1; }
  load(): void {}
}

function audioCue(items: Record<string, unknown>[]): PresentationCue {
  return {
    schemaVersion: 1,
    cueId: "cue-audio",
    planId: "plan-1",
    sequence: 0,
    kind: "audio",
    payload: { items },
    parallelGroup: "stage-1",
    blocking: false,
    completionState: "completed",
    skipState: "skipped",
    checkpoint: false,
  };
}

describe("WorldAudioMixer", () => {
  it("keeps independent channel levels and ducks music during voice playback", () => {
    const audios: FakeAudio[] = [];
    const mixer = new WorldAudioMixer({
      createAudio: (url) => {
        const audio = new FakeAudio();
        audio.src = url;
        audios.push(audio);
        return audio;
      },
      musicVolume: 80,
      ambienceVolume: 60,
      effectsVolume: 20,
    });

    mixer.playCue(audioCue([
      { kind: "music", audioUrl: "shiori-asset://local/music" },
      { kind: "ambience", audioUrl: "shiori-asset://local/rain" },
      { kind: "ui", audioUrl: "shiori-asset://local/click", loop: false },
    ]));
    assert.deepEqual(audios.map((audio) => audio.volume), [0.8, 0.6, 0.2]);
    mixer.voiceStarted();
    assert.deepEqual(audios.slice(1).map((audio) => audio.volume), [0.33, 0.2]);
    assert.ok(Math.abs(audios[0].volume - 0.44) < Number.EPSILON);
    mixer.voiceEnded();
    assert.deepEqual(audios.map((audio) => audio.volume), [0.8, 0.6, 0.2]);
  });

  it("replaces a channel and disposes its audio objects", () => {
    const audios: FakeAudio[] = [];
    const mixer = new WorldAudioMixer({ createAudio: (url) => { const audio = new FakeAudio(); audio.src = url; audios.push(audio); return audio; } });
    mixer.playCue(audioCue([{ kind: "music", audioUrl: "shiori-asset://local/old" }]));
    mixer.playCue(audioCue([{ kind: "music", audioUrl: "shiori-asset://local/new" }]));
    assert.equal(audios[0].pauseCount, 1);
    mixer.dispose();
    assert.equal(audios[1].pauseCount, 1);
    assert.equal(audios[1].src, "");
  });
});
