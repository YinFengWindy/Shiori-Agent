import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  createWheelGestureGate,
  narrativeAnchorStep,
  narrativeCgsToLoad,
  narrativeClickTarget,
  narrativeFinalOffset,
  narrativeStepAnchor,
  narrativeStepAt,
  narrativeStepOffset,
  narrativeStepTarget,
} from "../src/lib/narrativeModel";

const viewportHeight = 900;
const lineCount = 5;
const stepAt = (offset: number) => narrativeStepAt({ offset, viewportHeight, lineCount });

describe("narrativeStepAt", () => {
  it("shows step i on its snap point, i viewports below the section top", () => {
    assert.deepEqual([0, 900, 1800, 2700, 3600].map(stepAt), [0, 1, 2, 3, 4]);
  });

  it("flips to the next line halfway between two snap points, scrolling down or back up alike", () => {
    assert.equal(stepAt(449), 0);
    assert.equal(stepAt(450), 1);
    assert.equal(stepAt(1349), 1);
    assert.equal(stepAt(1351), 2);
  });

  it("shows the first line while the section is still below the viewport top", () => {
    assert.equal(stepAt(-1), 0);
    assert.equal(stepAt(-5000), 0);
  });

  it("has one more step after the last line: the download state", () => {
    // 4 × 900 is the last line's snap point; 5 × 900 the download state's.
    assert.equal(stepAt(3600), 4);
    assert.equal(stepAt(4049), 4);
    assert.equal(stepAt(4050), 5);
    assert.equal(stepAt(4500), 5);
  });

  it("stays on the download state once the page scrolls past the narrative", () => {
    assert.equal(stepAt(20000), 5);
  });

  it("follows the viewport height (mobile address bar, resize)", () => {
    assert.equal(narrativeStepAt({ offset: 1688, viewportHeight: 844, lineCount }), 2);
  });

  it("works for a one-line narrative", () => {
    assert.equal(narrativeStepAt({ offset: 0, viewportHeight, lineCount: 1 }), 0);
    assert.equal(narrativeStepAt({ offset: 3000, viewportHeight, lineCount: 1 }), 1);
  });

  it("rejects a layout it cannot map", () => {
    assert.throws(() => narrativeStepAt({ offset: 0, viewportHeight: 0, lineCount }), /viewportHeight/);
    assert.throws(() => narrativeStepAt({ offset: 0, viewportHeight, lineCount: 0 }), /lineCount/);
    assert.throws(() => narrativeStepAt({ offset: Number.NaN, viewportHeight, lineCount }), /offset/);
  });
});

describe("narrativeStepTarget", () => {
  const step = (offset: number, direction: 1 | -1) => narrativeStepTarget({ offset, viewportHeight, lineCount }, direction);

  it("steps one snap point down or back up from a line", () => {
    assert.equal(step(0, 1), 900);
    assert.equal(step(1800, 1), 2700);
    assert.equal(step(1800, -1), 900);
  });

  it("steps from the nearest snap point when the page sits between two", () => {
    assert.equal(step(1000, 1), 1800);
    assert.equal(step(1700, -1), 900);
  });

  it("steps from the last line onto the download state, and from it back onto the last line", () => {
    assert.equal(step(3600, 1), 4500);
    assert.equal(step(4500, -1), 3600);
  });

  it("steps from the download state onto the top of the content after the narrative, and from there back", () => {
    assert.equal(step(4500, 1), 5400);
    assert.equal(step(5400, -1), 4500);
    assert.equal(step(5000, 1), 5400);
    assert.equal(step(5000, -1), 4500);
  });

  it("leaves the browser to scroll above the first line and onward from the top of the content after the narrative", () => {
    assert.equal(step(0, -1), null);
    assert.equal(step(5400, 1), null);
    assert.equal(step(6000, -1), null);
    assert.equal(step(-2000, 1), null);
  });
});

describe("narrativeFinalOffset", () => {
  it("puts the download state one viewport below the last line", () => {
    assert.equal(narrativeFinalOffset({ viewportHeight, lineCount }), 4500);
  });
});

describe("narrativeClickTarget", () => {
  const click = (offset: number) => narrativeClickTarget({ offset, viewportHeight, lineCount });

  it("steps one line on, and from the last line onto the download state", () => {
    assert.equal(click(0), 900);
    assert.equal(click(3600), 4500);
  });

  it("stays put on the download state and below it, where a wheel step would leave the stage", () => {
    assert.equal(narrativeStepTarget({ offset: 4500, viewportHeight, lineCount }, 1), 5400);
    assert.equal(click(4500), null);
    assert.equal(click(5000), null);
    assert.equal(click(6000), null);
  });
});

describe("createWheelGestureGate", () => {
  it("steps once for a dense stream of wheel events (fast spin, trackpad swipe and its momentum)", () => {
    const gate = createWheelGestureGate(180);
    const steps = [0, 16, 32, 48, 120, 250, 400, 560].map(gate);
    assert.deepEqual(steps, [true, false, false, false, false, false, false, false]);
  });

  it("steps for every notch separated by a pause", () => {
    const gate = createWheelGestureGate(180);
    assert.deepEqual([0, 300, 600, 950].map(gate), [true, true, true, true]);
  });

  it("starts a new gesture after the stream goes quiet", () => {
    const gate = createWheelGestureGate(180);
    assert.deepEqual([0, 100, 200, 379, 560].map(gate), [true, false, false, false, true]);
  });
});

describe("narrativeCgsToLoad", () => {
  // Lines 0–1 without a CG, then a, b, b (one CG over two lines), none, c.
  const lineCgs = [undefined, undefined, "a", "b", "b", undefined, "c"] as const;

  it("loads nothing while the lines on stage and just ahead have no CG", () => {
    assert.deepEqual(narrativeCgsToLoad(lineCgs, 0, 1), []);
  });

  it("loads the CG on stage and those of the next `lookahead` lines, in order, without repeats", () => {
    assert.deepEqual(narrativeCgsToLoad(lineCgs, 0, 2), ["a"]);
    assert.deepEqual(narrativeCgsToLoad(lineCgs, 2, 2), ["a", "b"]);
    assert.deepEqual(narrativeCgsToLoad(lineCgs, 4, 2), ["b", "c"]);
    assert.deepEqual(narrativeCgsToLoad(lineCgs, 3, 0), ["b"]);
  });

  it("does not reach further ahead than the lookahead", () => {
    assert.deepEqual(narrativeCgsToLoad(lineCgs, 1, 1), ["a"]);
  });

  it("keeps the last line's CG under the download state (step = line count)", () => {
    assert.deepEqual(narrativeCgsToLoad(lineCgs, lineCgs.length, 2), ["c"]);
  });

  it("rejects a step outside the narrative", () => {
    assert.throws(() => narrativeCgsToLoad(lineCgs, -1));
    assert.throws(() => narrativeCgsToLoad(lineCgs, lineCgs.length + 1));
  });
});

describe("narrative anchors (#806)", () => {
  const anchors = { lineIds: ["arrival", "introduction", "companion", "characters", "remembers"], downloadId: "download" };

  it("opens the narrative on the step an address names: a line, or the download call after the last line", () => {
    assert.equal(narrativeAnchorStep("#arrival", anchors), 0);
    assert.equal(narrativeAnchorStep("#remembers", anchors), 4);
    assert.equal(narrativeAnchorStep("#download", anchors), 5);
  });

  it("leaves addresses naming no step of the narrative to the browser", () => {
    assert.equal(narrativeAnchorStep("", anchors), null);
    assert.equal(narrativeAnchorStep("#memory", anchors), null);
    assert.equal(narrativeAnchorStep("#%E0%A4%A", anchors), null);
  });

  it("names the step on show by its anchor, the download call past the last line", () => {
    assert.equal(narrativeStepAnchor(0, anchors), "arrival");
    assert.equal(narrativeStepAnchor(4, anchors), "remembers");
    assert.equal(narrativeStepAnchor(5, anchors), "download");
    assert.throws(() => narrativeStepAnchor(6, anchors));
    assert.throws(() => narrativeStepAnchor(-1, anchors));
  });

  it("round-trips: the anchor of a step opens the narrative on that step, where the step reads back", () => {
    for (let step = 0; step <= anchors.lineIds.length; step += 1) {
      const landed = narrativeAnchorStep(`#${narrativeStepAnchor(step, anchors)}`, anchors);
      assert.equal(landed, step);
      assert.ok(landed !== null);
      const offset = narrativeStepOffset(landed, { viewportHeight, lineCount: anchors.lineIds.length });
      assert.equal(narrativeStepAt({ offset, viewportHeight, lineCount: anchors.lineIds.length }), step);
    }
  });

  it("rejects anchors that would name two steps", () => {
    assert.throws(() => narrativeAnchorStep("#a", { lineIds: ["a", "a"], downloadId: "download" }));
    assert.throws(() => narrativeAnchorStep("#a", { lineIds: ["a"], downloadId: "a" }));
  });
});
