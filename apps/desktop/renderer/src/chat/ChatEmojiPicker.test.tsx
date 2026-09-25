/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React, { act, useState } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { ChatEmojiPicker } from "./ChatEmojiPicker";

/** Owns `open` the way ChatComposer does, recording the emojis picked. */
function PickerHarness({ picked }: { picked: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="composer" style={{ overflow: "hidden" }}>
      <ChatEmojiPicker
        disabled={false}
        open={open}
        onClose={() => setOpen(false)}
        onSelectEmoji={(emoji) => { picked.push(emoji); setOpen(false); }}
        onToggle={() => setOpen((current) => !current)}
      />
    </div>
  );
}

function panel(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[aria-label="常用表情面板"]');
}

function toggle(): HTMLButtonElement {
  const button = document.querySelector<HTMLButtonElement>('[aria-haspopup="dialog"]');
  assert.ok(button);
  return button;
}

async function press(key: string, init: KeyboardEventInit = {}) {
  await act(async () => {
    (document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, ...init }));
  });
}

describe("ChatEmojiPicker", () => {
  it("renders the open panel outside the clipping composer, pinned above the button", async () => {
    const view = await mountTestComponent(<PickerHarness picked={[]} />);
    try {
      assert.equal(panel(), null);
      await act(async () => { toggle().click(); });
      const opened = panel();
      assert.ok(opened);
      assert.equal(view.container.querySelector(".composer")?.contains(opened), false);
      const layer = opened.parentElement;
      assert.equal(layer?.parentElement, document.body);
      assert.match(layer?.className ?? "", /\bfixed\b/);
      assert.match(layer?.className ?? "", /motion-popover-enter/);
      assert.ok(layer?.style.bottom);
      assert.ok(opened.style.maxHeight);
      assert.equal(toggle().getAttribute("aria-label"), "收起常用表情面板");
    } finally { await view.cleanup(); }
  });

  it("moves keyboard focus into the grid and inserts the chosen emoji", async () => {
    const picked: string[] = [];
    const view = await mountTestComponent(<PickerHarness picked={picked} />);
    try {
      await act(async () => { toggle().click(); });
      assert.equal(document.activeElement?.getAttribute("aria-label"), "插入表情 😀");
      await act(async () => { (document.activeElement as HTMLButtonElement).click(); });
      assert.deepEqual(picked, ["😀"]);
      assert.equal(panel(), null);
    } finally { await view.cleanup(); }
  });

  it("closes on Escape and hands focus back to the button", async () => {
    const view = await mountTestComponent(<PickerHarness picked={[]} />);
    try {
      await act(async () => { toggle().click(); });
      await press("Escape");
      assert.equal(panel(), null);
      assert.equal(document.activeElement, toggle());
    } finally { await view.cleanup(); }
  });

  it("closes when Tab leaves either end of the grid instead of dropping focus at the end of the page", async () => {
    const view = await mountTestComponent(<PickerHarness picked={[]} />);
    try {
      await act(async () => { toggle().click(); });
      await press("Tab", { shiftKey: true });
      assert.equal(panel(), null);
      assert.equal(document.activeElement, toggle());

      await act(async () => { toggle().click(); });
      const buttons = panel()?.querySelectorAll<HTMLButtonElement>("button");
      await act(async () => { buttons?.[buttons.length - 1]?.focus(); });
      await press("Tab");
      assert.equal(panel(), null);
      assert.equal(document.activeElement, toggle());
    } finally { await view.cleanup(); }
  });

  it("closes on a pointer-down outside the panel but not inside it", async () => {
    const view = await mountTestComponent(<PickerHarness picked={[]} />);
    try {
      await act(async () => { toggle().click(); });
      await act(async () => { panel()?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })); });
      assert.ok(panel());
      await act(async () => { document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })); });
      assert.equal(panel(), null);
    } finally { await view.cleanup(); }
  });
});
