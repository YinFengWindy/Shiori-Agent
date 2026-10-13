import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { currentSectionIndex, postTableOfContents } from "../src/lib/sectionIndex";

describe("postTableOfContents", () => {
  it("lists the h2s with the h3s under them as sub-entries, leaving deeper headings out", () => {
    assert.deepEqual(
      postTableOfContents([
        { depth: 2, slug: "a", text: "A" },
        { depth: 3, slug: "a-1", text: "A.1" },
        { depth: 4, slug: "a-1-x", text: "A.1.x" },
        { depth: 2, slug: "b", text: "B" },
      ]),
      [
        { id: "a", label: "A", level: 0 },
        { id: "a-1", label: "A.1", level: 1 },
        { id: "b", label: "B", level: 0 },
      ],
    );
  });

  it("is empty for a post with fewer than two h2s, however many h3s it has", () => {
    assert.deepEqual(postTableOfContents([]), []);
    assert.deepEqual(
      postTableOfContents([
        { depth: 2, slug: "a", text: "A" },
        { depth: 3, slug: "a-1", text: "A.1" },
        { depth: 3, slug: "a-2", text: "A.2" },
      ]),
      [],
    );
  });

  it("drops an h3 that comes before any h2", () => {
    assert.deepEqual(
      postTableOfContents([
        { depth: 3, slug: "intro", text: "Intro" },
        { depth: 2, slug: "a", text: "A" },
        { depth: 2, slug: "b", text: "B" },
      ]).map((entry) => entry.id),
      ["a", "b"],
    );
  });

  it("fails on a heading without an id to link to", () => {
    assert.throws(() => postTableOfContents([{ depth: 2, slug: "", text: "A" }]));
  });
});

describe("currentSectionIndex", () => {
  const VIEWPORT = 900;
  const LINE = 80;

  it("marks nothing while the first section is still below the reading line", () => {
    assert.equal(currentSectionIndex({ tops: [300, 1200], line: LINE, atEnd: false, viewportHeight: VIEWPORT }), -1);
  });

  it("marks the last section whose top has reached the reading line", () => {
    assert.equal(currentSectionIndex({ tops: [-500, 40, 600], line: LINE, atEnd: false, viewportHeight: VIEWPORT }), 1);
    // A followed link stops a section a little above the line (scroll-margin), or at it after rounding.
    assert.equal(currentSectionIndex({ tops: [-500, LINE + 0.5, 600], line: LINE, atEnd: false, viewportHeight: VIEWPORT }), 1);
  });

  it("at the end of the page, marks the last section on screen even below the line", () => {
    const tops = [-900, 200, 500];
    assert.equal(currentSectionIndex({ tops, line: LINE, atEnd: false, viewportHeight: VIEWPORT }), 0);
    assert.equal(currentSectionIndex({ tops, line: LINE, atEnd: true, viewportHeight: VIEWPORT }), 2);
  });

  it("at the end of the page, leaves a section still off screen unmarked", () => {
    assert.equal(currentSectionIndex({ tops: [-900, 400, 1000], line: LINE, atEnd: true, viewportHeight: VIEWPORT }), 1);
  });
});
