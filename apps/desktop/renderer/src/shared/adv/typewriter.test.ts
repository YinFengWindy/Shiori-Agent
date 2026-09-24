import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { advanceTypewriter, startTypewriter } from "./typewriter";

const timing = { msPerChar: 40, reducedMotion: false };

describe("typewriter", () => {
  it("starts empty, or complete when reveals are instant", () => {
    assert.deepEqual(startTypewriter(5, timing), { shownChars: 0, pendingMs: 0 });
    assert.deepEqual(startTypewriter(5, { ...timing, reducedMotion: true }), { shownChars: 5, pendingMs: 0 });
    assert.deepEqual(startTypewriter(5, { ...timing, msPerChar: 0 }), { shownChars: 5, pendingMs: 0 });
  });

  it("carries leftover time into the next character", () => {
    const first = advanceTypewriter({ shownChars: 0, pendingMs: 0 }, 100, 10, timing);
    assert.deepEqual(first, { shownChars: 2, pendingMs: 20 });
    assert.deepEqual(advanceTypewriter(first, 20, 10, timing), { shownChars: 3, pendingMs: 0 });
  });

  it("stops at the line end and returns the same object once complete", () => {
    const done = advanceTypewriter({ shownChars: 0, pendingMs: 0 }, 1000, 4, timing);
    assert.deepEqual(done, { shownChars: 4, pendingMs: 0 });
    assert.equal(advanceTypewriter(done, 100, 4, timing), done);
  });
});
