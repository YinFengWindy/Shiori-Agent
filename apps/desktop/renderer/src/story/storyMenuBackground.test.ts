/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  chooseRandomStoryMenuAsset,
  collectStoryMenuAssetCandidates,
  loadLandscapeStoryMenuAssets,
  type StoryMenuImageProbe,
} from "./storyMenuBackground";

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

describe("storyMenuBackground", () => {
  it("keeps role ownership while collecting illustration paths", () => {
    const candidates = collectStoryMenuAssetCandidates([
      { id: "role-a", illustrations_abs: ["a-wide.png", "a-tall.png"] },
      { id: "role-b", illustrations_abs: [] },
    ], (path) => `asset://${path}`);

    assert.deepEqual(candidates, [
      { roleId: "role-a", assetPath: "a-wide.png", assetUrl: "asset://a-wide.png" },
      { roleId: "role-a", assetPath: "a-tall.png", assetUrl: "asset://a-tall.png" },
    ]);
  });

  it("filters out portrait, square, and failed image probes", async () => {
    const candidates = [
      { roleId: "role-a", assetPath: "wide.png", assetUrl: "asset://wide.png" },
      { roleId: "role-a", assetPath: "square.png", assetUrl: "asset://square.png" },
      { roleId: "role-b", assetPath: "broken.png", assetUrl: "asset://broken.png" },
    ];
    const landscape = await loadLandscapeStoryMenuAssets(
      candidates,
      () => new FakeImage({
        "asset://wide.png": [1600, 900],
        "asset://square.png": [1000, 1000],
      }),
    );

    assert.deepEqual(landscape, [candidates[0]]);
  });

  it("chooses a role first and then an asset owned by that role", () => {
    const candidates = [
      { roleId: "role-a", assetPath: "a-1.png", assetUrl: "asset://a-1.png" },
      { roleId: "role-a", assetPath: "a-2.png", assetUrl: "asset://a-2.png" },
      { roleId: "role-b", assetPath: "b-1.png", assetUrl: "asset://b-1.png" },
    ];

    assert.deepEqual(
      chooseRandomStoryMenuAsset(candidates, (() => {
        const values = [0, 0.99];
        return () => values.shift() ?? 0;
      })()),
      candidates[1],
    );
  });
});
