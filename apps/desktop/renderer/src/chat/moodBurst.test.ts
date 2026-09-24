/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { Window } from "happy-dom";
import { moodBurstParticles, moodParticleCap, spawnMoodParticles, type MoodBurstGeometry } from "./moodBurst";
import type { MoodTone } from "./moodTone";

const geometry: MoodBurstGeometry = { frame: { x: 12, y: 8, width: 220, height: 200 }, pill: { x: 190, y: 240 } };
const tones: MoodTone[] = ["happy", "shy", "sad", "angry", "calm"];

/** A deterministic random source. */
function seeded(seed = 7) {
  let state = seed;
  return () => {
    state = (state * 16807) % 2147483647;
    return state / 2147483647;
  };
}

describe("moodBurstParticles", () => {
  it("uses each tone's brand motif", () => {
    const kinds = (tone: MoodTone) => [...new Set(moodBurstParticles(tone, geometry, seeded()).map((particle) => particle.kind))].sort();
    assert.deepEqual(kinds("happy"), ["petal"]);
    assert.deepEqual(kinds("shy"), ["heart"]);
    assert.deepEqual(kinds("sad"), ["droplet"]);
    assert.deepEqual(kinds("angry"), ["sparkle"]);
    assert.deepEqual(kinds("calm"), ["halo", "sparkle"]);
  });

  it("keeps every burst short and within the live cap", () => {
    for (const tone of tones) {
      const particles = moodBurstParticles(tone, geometry, seeded());
      assert.ok(particles.length > 0 && particles.length <= moodParticleCap, tone);
      for (const particle of particles) {
        assert.ok(particle.delay + particle.duration <= 1600, `${tone} lasts ${particle.delay + particle.duration}ms`);
        assert.equal(particle.keyframes.at(-1)?.opacity, 0, `${tone} ends invisible`);
      }
    }
  });

  it("starts the sparks at the pill and the petals above the portrait", () => {
    for (const spark of moodBurstParticles("angry", geometry, seeded())) {
      assert.equal(spark.x + spark.size / 2, geometry.pill.x);
      assert.equal(spark.y + spark.size / 2, geometry.pill.y);
      assert.ok(spark.shade >= 1, "sparks use the red shades");
    }
    for (const petal of moodBurstParticles("happy", geometry, seeded())) {
      assert.ok(petal.y < geometry.frame.y);
    }
  });
});

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

  it("draws motifs as svg paths and the halo as a plain disc", async () => {
    const { layer, close } = fakeLayer();
    try {
      spawnMoodParticles(layer, moodBurstParticles("calm", geometry, seeded()));
      const [halo, sparkle] = Array.from(layer.children);
      assert.equal(halo!.getAttribute("data-particle"), "halo");
      assert.equal(halo!.querySelector("svg"), null);
      assert.equal(sparkle!.getAttribute("data-particle"), "sparkle");
      assert.ok(sparkle!.querySelector("path")?.getAttribute("d"));
    } finally {
      await close();
    }
  });
});
