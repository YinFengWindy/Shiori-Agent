/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveWorldLoadingPresentation } from "./worldLoadingPolicy";

describe("resolveWorldLoadingPresentation", () => {
  it("keeps sub-250ms loads invisible", () => {
    assert.equal(resolveWorldLoadingPresentation({ elapsedMs: 249, loaded: 0, total: 3 }).kind, "hidden");
  });

  it("uses a short chapter transition before two seconds", () => {
    assert.equal(resolveWorldLoadingPresentation({ elapsedMs: 800, loaded: 1, total: 3 }).kind, "transition");
  });

  it("shows measurable progress after two seconds", () => {
    assert.deepEqual(
      resolveWorldLoadingPresentation({ elapsedMs: 2400, loaded: 3, total: 8 }),
      { kind: "progress", loaded: 3, total: 8, ratio: 3 / 8 },
    );
  });
});
