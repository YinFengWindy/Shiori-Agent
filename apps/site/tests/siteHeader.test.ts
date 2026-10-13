import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isPastNarrative } from "../src/lib/siteHeader";

const VIEWPORT = 900;

describe("isPastNarrative", () => {
  it("keeps the bar away on every narrative step, the download state included", () => {
    // The sticky stage fills the viewport until the section's bottom reaches the viewport's bottom.
    assert.equal(isPastNarrative(VIEWPORT * 15, VIEWPORT), false);
    assert.equal(isPastNarrative(VIEWPORT, VIEWPORT), false);
  });

  it("shows the bar once the showcase fills most of the screen, and from there on down", () => {
    assert.equal(isPastNarrative(VIEWPORT / 2, VIEWPORT), true);
    assert.equal(isPastNarrative(0, VIEWPORT), true);
    assert.equal(isPastNarrative(-VIEWPORT * 4, VIEWPORT), true);
  });

  it("hides it again as soon as scrolling back brings the narrative over half the screen", () => {
    assert.equal(isPastNarrative(VIEWPORT / 2 + 1, VIEWPORT), false);
  });

  it("rejects a viewport or position that cannot be measured", () => {
    assert.throws(() => isPastNarrative(0, 0));
    assert.throws(() => isPastNarrative(Number.NaN, VIEWPORT));
  });
});
