/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { advanceCrossfadeLayers, initialCrossfadeLayers, settleCrossfadeLayers } from "./crossfadeLayerState";

describe("crossfade layers", () => {
  it("fades the shown image out while the next fades in", () => {
    const next = advanceCrossfadeLayers(initialCrossfadeLayers("a.png"), "b.png", false);
    assert.deepEqual(next.map(({ value, phase }) => [value, phase]), [["a.png", "out"], ["b.png", "in"]]);
  });

  it("settles into one static layer", () => {
    const next = settleCrossfadeLayers(advanceCrossfadeLayers(initialCrossfadeLayers("a.png"), "b.png", false));
    assert.deepEqual(next.map(({ value, phase }) => [value, phase]), [["b.png", "static"]]);
  });

  it("swaps instantly for a new subject or from nothing", () => {
    assert.deepEqual(advanceCrossfadeLayers(initialCrossfadeLayers("a.png"), "b.png", true).map((layer) => layer.phase), ["static"]);
    assert.deepEqual(advanceCrossfadeLayers(initialCrossfadeLayers(""), "b.png", false).map((layer) => layer.phase), ["static"]);
  });

  it("drops a layer still fading out when the value changes again", () => {
    const twice = advanceCrossfadeLayers(advanceCrossfadeLayers(initialCrossfadeLayers("a.png"), "b.png", false), "c.png", false);
    assert.deepEqual(twice.map(({ value, phase }) => [value, phase]), [["b.png", "out"], ["c.png", "in"]]);
  });

  it("keeps the same array when the value did not change", () => {
    const layers = initialCrossfadeLayers("a.png");
    assert.equal(advanceCrossfadeLayers(layers, "a.png", false), layers);
    assert.equal(settleCrossfadeLayers(layers), layers);
  });

  it("gives every new value a fresh key so React remounts the layer", () => {
    const next = advanceCrossfadeLayers(initialCrossfadeLayers("a.png"), "b.png", false);
    assert.notEqual(next[0]!.key, next[1]!.key);
  });
});
