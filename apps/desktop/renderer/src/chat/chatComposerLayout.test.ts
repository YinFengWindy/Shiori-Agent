/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { chatComposerLineHeightPx, getChatComposerLimits } from "./chatComposerLayout";

describe("getChatComposerLimits", () => {
  it("caps the textarea at 10 lines in a tall pane", () => {
    assert.equal(getChatComposerLimits(1000).textareaMaxHeight, chatComposerLineHeightPx * 10);
  });

  it("caps the textarea at 40% of a short pane", () => {
    assert.equal(getChatComposerLimits(500).textareaMaxHeight, 200);
  });

  it("keeps the whole composer below the chat header", () => {
    const limits = getChatComposerLimits(500);
    assert.ok((limits.composerMaxHeight ?? Infinity) + 40 < 500);
    // Even with every part at its cap, what the composer shows fits in its own cap by scrolling.
    assert.ok(limits.attachmentsMaxHeight <= 128);
  });

  it("falls back to the line cap before the pane is measured", () => {
    const limits = getChatComposerLimits(0);
    assert.equal(limits.textareaMaxHeight, 240);
    assert.equal(limits.composerMaxHeight, undefined);
  });
});
