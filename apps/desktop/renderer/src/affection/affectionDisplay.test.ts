import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { resolveAffectionDisplay } from "./affectionDisplay";

describe("resolveAffectionDisplay", () => {
  it("fills the bar to the value's place on the whole -100–100 range, whatever the in-stage progress", () => {
    assert.deepEqual(resolveAffectionDisplay({ value: 95, stage: "挚爱", progress: 0.75, floor: 80 }), { stage: "挚爱", percent: 97.5 });
    assert.deepEqual(resolveAffectionDisplay({ value: 0, stage: "陌生", progress: 0, floor: null }), { stage: "陌生", percent: 50 });
    assert.deepEqual(resolveAffectionDisplay({ value: -30, stage: "冷淡", progress: 19 / 48, floor: null }), { stage: "冷淡", percent: 35 });
    assert.deepEqual(resolveAffectionDisplay({ value: -100, stage: "厌恶", progress: 0, floor: null }), { stage: "厌恶", percent: 0 });
  });

  it("shows nothing before initialization or for malformed summaries", () => {
    assert.equal(resolveAffectionDisplay(null), null);
    assert.equal(resolveAffectionDisplay(undefined), null);
    assert.equal(resolveAffectionDisplay({ value: Number.NaN, stage: "陌生", progress: 0.5, floor: null }), null);
    assert.equal(resolveAffectionDisplay({ value: 10, progress: 0.5 } as unknown as AffectionSummary), null);
  });
});
