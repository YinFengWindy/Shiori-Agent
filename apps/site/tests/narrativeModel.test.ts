import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createWheelGestureGate, narrativeStepAt, narrativeStepTarget } from "../src/lib/narrativeModel";

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

  it("leaves the browser to scroll above the first line and onward from the download state", () => {
    assert.equal(step(0, -1), null);
    assert.equal(step(4500, 1), null);
    assert.equal(step(5200, -1), null);
    assert.equal(step(-2000, 1), null);
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
