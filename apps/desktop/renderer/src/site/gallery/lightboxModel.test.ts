/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { closeLightbox, createLightbox, lightboxCounter, openLightbox, stepLightbox, wrapIndex } from "./lightboxModel";

describe("wrapIndex", () => {
  it("keeps in-range indices and wraps both ends", () => {
    assert.equal(wrapIndex(3, 10), 3);
    assert.equal(wrapIndex(10, 10), 0);
    assert.equal(wrapIndex(-1, 10), 9);
    assert.equal(wrapIndex(-11, 10), 9);
    assert.equal(wrapIndex(23, 10), 3);
  });

  it("rejects a non-positive count or a fractional index", () => {
    assert.throws(() => wrapIndex(0, 0));
    assert.throws(() => wrapIndex(0, -3));
    assert.throws(() => wrapIndex(1.5, 3));
  });
});

describe("lightbox state", () => {
  it("starts closed on the first image", () => {
    assert.deepEqual(createLightbox(10), { open: false, index: 0, count: 10 });
    assert.throws(() => createLightbox(0));
  });

  it("opens on the chosen image and rejects out-of-range indices", () => {
    const opened = openLightbox(createLightbox(10), 4);
    assert.deepEqual(opened, { open: true, index: 4, count: 10 });
    assert.throws(() => openLightbox(createLightbox(10), 10));
    assert.throws(() => openLightbox(createLightbox(10), -1));
  });

  it("steps forward and back with wrap-around", () => {
    const last = openLightbox(createLightbox(10), 9);
    assert.equal(stepLightbox(last, 1).index, 0);
    const first = openLightbox(createLightbox(10), 0);
    assert.equal(stepLightbox(first, -1).index, 9);
    assert.equal(stepLightbox(stepLightbox(first, 1), 1).index, 2);
  });

  it("ignores steps while closed", () => {
    const closed = createLightbox(10);
    assert.equal(stepLightbox(closed, 1), closed);
  });

  it("closes but remembers the last image so focus can return to its thumbnail", () => {
    const viewed = stepLightbox(openLightbox(createLightbox(10), 2), 1);
    const closed = closeLightbox(viewed);
    assert.deepEqual(closed, { open: false, index: 3, count: 10 });
    assert.equal(closeLightbox(closed), closed);
  });

  it("formats a 1-based counter", () => {
    assert.equal(lightboxCounter(openLightbox(createLightbox(10), 2)), "3 / 10");
    assert.equal(lightboxCounter(openLightbox(createLightbox(10), 9)), "10 / 10");
  });
});
