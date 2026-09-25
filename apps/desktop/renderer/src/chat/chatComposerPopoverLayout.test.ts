import assert from "node:assert/strict";
import test from "node:test";
import { getChatComposerPopoverPosition } from "./chatComposerPopoverLayout";

test("anchors the popover bottom above the trigger, left edges aligned", () => {
  assert.deepEqual(
    getChatComposerPopoverPosition({ left: 24, right: 54, top: 300 }, { width: 1000, height: 500 }, 240),
    { left: 24, bottom: 204, maxHeight: 288 },
  );
});

test("end alignment lines the popover's right edge up with the trigger's", () => {
  const position = getChatComposerPopoverPosition(
    { left: 820, right: 850, top: 700 },
    { width: 1280, height: 800 },
    232,
    { align: "end", gap: 10 },
  );
  assert.equal(position.left, 850 - 232);
  assert.equal(position.bottom, 800 - 700 + 10);
});

test("keeps the popover inside a narrow window on either alignment", () => {
  assert.equal(getChatComposerPopoverPosition({ left: 700, right: 730, top: 300 }, { width: 800, height: 500 }, 240).left, 552);
  assert.equal(
    getChatComposerPopoverPosition({ left: 100, right: 130, top: 300 }, { width: 800, height: 500 }, 240, { align: "end" }).left,
    8,
  );
});

test("limits the popover to the room above the trigger so it scrolls instead of overflowing", () => {
  assert.equal(getChatComposerPopoverPosition({ left: 24, right: 54, top: 200 }, { width: 1000, height: 800 }, 240).maxHeight, 188);
  // A short window: the emoji panel (about 196px tall) no longer fits and must scroll.
  assert.equal(
    getChatComposerPopoverPosition({ left: 820, right: 850, top: 150 }, { width: 1280, height: 220 }, 232, { align: "end", gap: 10 }).maxHeight,
    132,
  );
});

test("never shrinks the popover below a usable height", () => {
  assert.equal(getChatComposerPopoverPosition({ left: 24, right: 54, top: 40 }, { width: 1000, height: 100 }, 240).maxHeight, 120);
});
