/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PresentationCue } from "./presentationProtocol";
import { defaultWorldGameSettings } from "./worldGameSettingsStore";
import { WorldPresentationRuntime } from "./worldPresentationRuntime";

const dialogueCue: PresentationCue = {
  schemaVersion: 1,
  cueId: "cue-1",
  planId: "plan-1",
  sequence: 0,
  kind: "dialogue",
  payload: { content: "潮声正在靠近。" },
  parallelGroup: null,
  blocking: true,
  completionState: "completed",
  skipState: "skipped",
  checkpoint: true,
};

describe("WorldPresentationRuntime", () => {
  it("keeps a dialogue cue pending until reveal and advance", async () => {
    const runtime = new WorldPresentationRuntime({
      readSettings: () => ({ ...defaultWorldGameSettings, autoPlay: false, showFullText: false }),
      createWorldAudio: () => { throw new Error("unexpected audio"); },
    });
    const completion = runtime.handleRenderedCue({ ...dialogueCue, payload: { ...dialogueCue.payload, speakerName: "澪" } }, "world-1") as Promise<void>;
    let completed = false;
    void completion.then(() => { completed = true; });

    assert.equal(runtime.dialogueSnapshot().speakerName, "澪");
    assert.equal(runtime.continueDialogue(), "revealed");
    await Promise.resolve();
    assert.equal(completed, false);
    assert.equal(runtime.continueDialogue(), "advanced");
    await completion;
    runtime.dispose();
  });

  it("reuses retained stage resources and disposes them with the route runtime", () => {
    const runtime = new WorldPresentationRuntime({
      readSettings: () => defaultWorldGameSettings,
      createWorldAudio: () => { throw new Error("unexpected audio"); },
    });
    let created = 0;
    let disposed = 0;
    const first = runtime.retainStageResource("pixi-assets", () => ({ id: ++created }), () => { disposed += 1; });
    const second = runtime.retainStageResource("pixi-assets", () => ({ id: ++created }), () => { disposed += 1; });

    assert.equal(first, second);
    assert.equal(created, 1);
    runtime.dispose();
    assert.equal(disposed, 1);
  });

  it("reveals unread dialogue before the skip setting can advance it", async () => {
    const runtime = new WorldPresentationRuntime({
      readSettings: () => ({ ...defaultWorldGameSettings, skipReadTextOnly: true }),
      createWorldAudio: () => { throw new Error("unexpected audio"); },
    });
    const completion = runtime.handleRenderedCue(dialogueCue, "world-1") as Promise<void>;

    runtime.skipDialogue();
    assert.equal(runtime.dialogueSnapshot().fullyRevealed, true);
    assert.equal(runtime.dialogueSnapshot().cueId, "cue-1");
    runtime.skipDialogue();
    await completion;
    assert.equal(runtime.dialogueSnapshot().cueId, null);
    runtime.dispose();
  });
});
