/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { Window } from "happy-dom";
import { moodBurstParticles, moodParticleCap, spawnMoodParticles, type MoodBurstGeometry } from "./moodBurst";

const geometry: MoodBurstGeometry = { frame: { x: 12, y: 8, width: 220, height: 200 }, pill: { x: 190, y: 240 } };

/** A deterministic random source. */
function seeded(seed = 7) {
  let state = seed;
  return () => {
    state = (state * 16807) % 2147483647;
    return state / 2147483647;
  };
}

describe("spawnMoodParticles", () => {
  function fakeLayer() {
    const window = new Window();
    const layer = window.document.createElement("div");
    window.document.body.append(layer);
    const animations: Array<{ onfinish: (() => void) | null; oncancel: (() => void) | null }> = [];
    // happy-dom has no Web Animations; record what would run.
    Object.defineProperty(window.HTMLElement.prototype, "animate", {
      configurable: true,
      value() {
        const animation = { onfinish: null, oncancel: null };
        animations.push(animation);
        return animation;
      },
    });
    return { layer: layer as unknown as HTMLElement, animations, close: () => window.happyDOM.close() };
  }

  it("never keeps more than the cap alive, dropping the oldest", async () => {
    const { layer, close } = fakeLayer();
    try {
      const burst = moodBurstParticles("happy", geometry, seeded());
      spawnMoodParticles(layer, burst);
      spawnMoodParticles(layer, burst);
      spawnMoodParticles(layer, burst);
      assert.equal(burst.length * 3 > moodParticleCap, true);
      assert.equal(layer.childElementCount, moodParticleCap);
    } finally {
      await close();
    }
  });

  it("removes each particle when its animation finishes or is cancelled", async () => {
    const { layer, animations, close } = fakeLayer();
    try {
      spawnMoodParticles(layer, moodBurstParticles("calm", geometry, seeded()));
      assert.equal(layer.childElementCount, 2);
      animations[0]!.onfinish?.();
      assert.equal(layer.childElementCount, 1);
      animations[1]!.oncancel?.();
      assert.equal(layer.childElementCount, 0);
    } finally {
      await close();
    }
  });
});
