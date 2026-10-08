import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { resolveAffectionDisplay } from "./affectionDisplay";

describe("resolveAffectionDisplay", () => {
  it("maps the stage progress to a bar width", () => {
    assert.deepEqual(resolveAffectionDisplay({ value: 70, stage: "亲密", progress: 0.5 }), { stage: "亲密", percent: 50 });
    assert.deepEqual(resolveAffectionDisplay({ value: 100, stage: "挚爱", progress: 1.4 }), { stage: "挚爱", percent: 100 });
  });

  it("fills negative stages by their own progress, never below an empty bar", () => {
    assert.deepEqual(resolveAffectionDisplay({ value: -25, stage: "冷淡", progress: 0.5 }), { stage: "冷淡", percent: 50 });
    assert.deepEqual(resolveAffectionDisplay({ value: -100, stage: "厌恶", progress: -0.2 }), { stage: "厌恶", percent: 0 });
  });

  it("shows nothing before initialization or for malformed summaries", () => {
    assert.equal(resolveAffectionDisplay(null), null);
    assert.equal(resolveAffectionDisplay(undefined), null);
    assert.equal(resolveAffectionDisplay({ value: 10, stage: "陌生", progress: Number.NaN }), null);
    assert.equal(resolveAffectionDisplay({ value: 10, progress: 0.5 } as unknown as AffectionSummary), null);
  });
});
