/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  createStoryMenuTheme,
  extractDominantStoryMenuColor,
} from "./storyMenuTheme";

describe("storyMenuTheme", () => {
  it("extracts the most common saturated color and ignores transparent pixels", () => {
    const color = extractDominantStoryMenuColor(Uint8ClampedArray.from([
      224, 32, 32, 255,
      224, 32, 32, 255,
      32, 96, 224, 255,
      0, 0, 0, 0,
    ]));

    assert.deepEqual(color, { r: 224, g: 32, b: 32 });
  });

  it("does not force a theme from grayscale pixels", () => {
    assert.equal(extractDominantStoryMenuColor(Uint8ClampedArray.from([
      80, 80, 80, 255,
      220, 220, 220, 255,
    ])), null);
  });

  it("maps the sampled color to a launcher filter and title highlight", () => {
    const theme = createStoryMenuTheme({ r: 32, g: 160, b: 224 });

    assert.match(theme.commandFilter, /^hue-rotate\(-?\d+deg\) saturate\(\d+\.\d{2}\)$/);
    assert.equal(theme.titleHighlight, "rgba(32,160,224,0.35)");
  });
});
