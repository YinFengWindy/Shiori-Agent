/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { WorldDialogueGate } from "./worldDialogueGate";

describe("WorldDialogueGate", () => {
  it("reveals the full line before a second continue advances it", async () => {
    const gate = new WorldDialogueGate({ showFullText: false, autoPlay: false, autoPlayDelayMs: 800 });
    const completion = gate.present({ cueId: "cue-1", text: "潮声正在靠近。" });
    let completed = false;
    void completion.then(() => { completed = true; });

    assert.equal(gate.snapshot().fullyRevealed, false);
    assert.equal(gate.continue(), "revealed");
    assert.equal(gate.snapshot().fullyRevealed, true);
    await Promise.resolve();
    assert.equal(completed, false);

    assert.equal(gate.continue(), "advanced");
    await completion;
    assert.equal(gate.snapshot().cueId, null);
  });

  it("keeps voice playing on reveal and stops it only when advancing", async () => {
    let stopped = 0;
    const gate = new WorldDialogueGate({ showFullText: false, autoPlay: false, autoPlayDelayMs: 800 });
    const completion = gate.present({ cueId: "cue-voice", text: "别回头。", stopVoice: () => { stopped += 1; } });

    gate.continue();
    assert.equal(stopped, 0);
    gate.continue();
    await completion;
    assert.equal(stopped, 1);
  });

  it("advances automatically only after voice and the configured delay", async () => {
    let finishVoice!: () => void;
    const voiceFinished = new Promise<void>((resolve) => { finishVoice = resolve; });
    let runDelay!: () => void;
    const gate = new WorldDialogueGate(
      { showFullText: true, autoPlay: true, autoPlayDelayMs: 1200 },
      (callback, delayMs) => {
        assert.equal(delayMs, 1200);
        runDelay = callback;
        return () => undefined;
      },
    );
    const completion = gate.present({ cueId: "cue-auto", text: "天亮了。", voiceFinished });
    finishVoice();
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.ok(runDelay);
    runDelay();
    await completion;
  });
});
