import assert from "node:assert/strict";
import test from "node:test";
import { ensurePlaybackContextRunning } from "./playbackController";

test("resumes a suspended hidden playback context", async () => {
  const context = {
    state: "suspended" as AudioContextState,
    async resume() {
      this.state = "running";
    },
  };

  await ensurePlaybackContextRunning(context);

  assert.equal(context.state, "running");
});

test("fails instead of hanging when autoplay keeps playback suspended", async () => {
  const context = {
    state: "suspended" as AudioContextState,
    resume: () => new Promise<void>(() => undefined),
  };

  await assert.rejects(
    ensurePlaybackContextRunning(context, 1),
    /自动播放策略阻止/,
  );
});
