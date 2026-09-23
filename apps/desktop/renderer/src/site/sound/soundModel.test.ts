/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SFX_RECIPES, shouldPlayBgm, volumeToGain, type SfxName } from "./soundModel";

describe("volumeToGain", () => {
  it("is silent at 0 and unity at 100", () => {
    assert.equal(volumeToGain(0), 0);
    assert.equal(volumeToGain(100), 1);
  });

  it("follows a decibel curve rather than a linear one", () => {
    // Half the slider is -20 dB (0.1), not half the amplitude.
    assert.ok(Math.abs(volumeToGain(50) - 0.1) < 1e-9);
    assert.ok(Math.abs(volumeToGain(1) - 10 ** (-39.6 / 20)) < 1e-9);
  });

  it("rises monotonically across the slider", () => {
    for (let volume = 1; volume <= 100; volume++) {
      assert.ok(volumeToGain(volume) > volumeToGain(volume - 1), `step ${volume}`);
    }
  });

  it("clamps out-of-range values", () => {
    assert.equal(volumeToGain(-5), 0);
    assert.equal(volumeToGain(250), 1);
  });
});

describe("shouldPlayBgm", () => {
  const on = { soundEnabled: true, track: "bgm.mp3", hasContext: true };

  it("plays only with sound on, a track and a context", () => {
    assert.equal(shouldPlayBgm(on), true);
    assert.equal(shouldPlayBgm({ ...on, soundEnabled: false }), false);
    assert.equal(shouldPlayBgm({ ...on, track: null }), false);
    assert.equal(shouldPlayBgm({ ...on, hasContext: false }), false);
  });
});

describe("SFX_RECIPES", () => {
  const names = Object.keys(SFX_RECIPES) as SfxName[];
  const loudest = (name: SfxName) => Math.max(...SFX_RECIPES[name].voices.map((voice) => voice.peak));

  it("stays quiet and short", () => {
    for (const name of names) {
      const recipe = SFX_RECIPES[name];
      assert.ok(recipe.voices.length > 0, name);
      assert.ok(loudest(name) <= 0.15, `${name} peak`);
      assert.ok(recipe.attack > 0 && recipe.attack < 0.02, `${name} attack`);
      assert.ok(recipe.release > 0 && recipe.release <= 0.4, `${name} release`);
    }
  });

  it("uses audible, positive frequencies (exponential ramps need > 0)", () => {
    for (const name of names) {
      for (const voice of SFX_RECIPES[name].voices) {
        assert.ok(voice.frequency >= 200 && voice.frequency <= 5000, `${name} ${voice.frequency}`);
        if (voice.endFrequency !== undefined) assert.ok(voice.endFrequency > 0, `${name} glide`);
        assert.ok(voice.delay >= 0, `${name} delay`);
      }
    }
  });

  it("keeps the hover tick the quietest effect", () => {
    for (const name of names) {
      if (name !== "hover") assert.ok(loudest("hover") < loudest(name), name);
    }
  });
});
