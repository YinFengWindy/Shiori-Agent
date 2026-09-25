/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { aboutIdleLines, aboutUpdateLines } from "../shared/mascot/mascotLines";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { AboutMascot } from "./AboutMascot";

function said(container: HTMLElement) {
  return {
    text: container.querySelector('[data-testid="mascot-line"] .mascot-bubble-text')?.textContent ?? "",
    expression: container.querySelector('[data-testid="mascot-half"]')?.getAttribute("data-expression") ?? "",
  };
}

describe("AboutMascot", () => {
  it("opens on an idle line and draws a different one, with its face, on every click", async () => {
    const view = await mountTestComponent(<AboutMascot phase="idle"><div>版本卡片</div></AboutMascot>);
    try {
      assert.match(view.container.textContent ?? "", /版本卡片/);
      let previous = said(view.container);
      assert.ok(aboutIdleLines.some((line) => line.text === previous.text));
      const figure = view.container.querySelector<HTMLButtonElement>('button[aria-label="吟风"]')!;
      for (let click = 0; click < 4; click += 1) {
        await act(async () => figure.click());
        const next = said(view.container);
        assert.notEqual(next.text, previous.text);
        assert.equal(next.expression, aboutIdleLines.find((line) => line.text === next.text)?.expression);
        previous = next;
      }
    } finally {
      await view.cleanup();
    }
  });

  it("announces the update check's outcome", async () => {
    const view = await mountTestComponent(<AboutMascot phase="checking"><div /></AboutMascot>);
    try {
      await view.render(<AboutMascot phase="current"><div /></AboutMascot>);
      assert.deepEqual(said(view.container), aboutUpdateLines.current);
      await view.render(<AboutMascot phase="downloaded"><div /></AboutMascot>);
      assert.deepEqual(said(view.container), aboutUpdateLines.available);
    } finally {
      await view.cleanup();
    }
  });

  it("worries when the page's update request fails, as the plain error below leaves the talking to her", async () => {
    const view = await mountTestComponent(<AboutMascot phase="idle"><div /></AboutMascot>);
    try {
      await view.render(<AboutMascot phase="idle" failed><div /></AboutMascot>);
      assert.deepEqual(said(view.container), aboutUpdateLines.failed);
    } finally {
      await view.cleanup();
    }
  });
});
