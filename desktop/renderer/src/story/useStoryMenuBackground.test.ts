/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveStoryMenuBackground } from "./useStoryMenuBackground";
import type { StoryMenuImageProbe } from "./storyMenuBackground";
import { STORY_MENU_BACKGROUND_URL } from "./storyStaticAssets";

class FakeImage implements StoryMenuImageProbe {
  naturalWidth = 0;
  naturalHeight = 0;
  onload: StoryMenuImageProbe["onload"] = null;
  onerror: StoryMenuImageProbe["onerror"] = null;
  private currentSrc = "";

  constructor(private readonly dimensions: Record<string, [number, number]>) {}

  get src(): string {
    return this.currentSrc;
  }

  set src(value: string) {
    this.currentSrc = value;
    const size = this.dimensions[value];
    queueMicrotask(() => {
      if (!size) {
        if (this.onerror) Reflect.apply(this.onerror, this, [new Event("error")]);
        return;
      }
      [this.naturalWidth, this.naturalHeight] = size;
      if (this.onload) Reflect.apply(this.onload, this, [new Event("load")]);
    });
  }
}

describe("resolveStoryMenuBackground", () => {
  it("returns the random landscape asset after probing role libraries", async () => {
    const background = await resolveStoryMenuBackground([
      { id: "role-a", illustrations_abs: ["a-tall.png", "a-wide.png"] },
      { id: "role-b", illustrations_abs: ["b-wide.png"] },
    ], {
      resolveAssetUrl: (path) => `asset://${path}`,
      createImage: () => new FakeImage({
        "asset://a-tall.png": [900, 1600],
        "asset://a-wide.png": [1600, 900],
        "asset://b-wide.png": [1920, 1080],
      }),
      random: () => 0,
    });

    assert.equal(background, "asset://a-wide.png");
  });

  it("falls back to the bundled background when no landscape asset is available", async () => {
    const background = await resolveStoryMenuBackground([
      { id: "role-a", illustrations_abs: ["a-tall.png"] },
    ], {
      resolveAssetUrl: (path) => `asset://${path}`,
      createImage: () => new FakeImage({ "asset://a-tall.png": [900, 1600] }),
    });

    assert.equal(background, STORY_MENU_BACKGROUND_URL);
  });
});
