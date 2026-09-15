import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { listenForChatScrollIntent } from "./chatScrollIntent";

describe("listenForChatScrollIntent", () => {
  it("recognizes upward wheel, touch, keyboard and scrollbar input but ignores programmatic corrections", async () => {
    const view = await mountTestComponent(createElement("div", null, createElement("input")));
    const container = view.container.firstElementChild as HTMLDivElement;
    let departures = 0;
    container.scrollTop = 600;
    const cleanup = listenForChatScrollIntent(container, () => { departures += 1; });
    try {
      container.scrollTop = 500;
      container.dispatchEvent(new Event("scroll"));
      assert.equal(departures, 0);
      container.dispatchEvent(Object.assign(new Event("wheel"), { deltaY: -10 }));
      assert.equal(departures, 1);
      const touch = (type: string, clientY: number) => {
        const event = new Event(type);
        Object.defineProperty(event, "touches", { value: [{ clientY }] });
        container.dispatchEvent(event);
      };
      touch("touchstart", 100);
      touch("touchmove", 140);
      assert.equal(departures, 2);
      container.dispatchEvent(new KeyboardEvent("keydown", { key: "PageUp", bubbles: true }));
      assert.equal(departures, 3);
      container.querySelector("input")!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
      assert.equal(departures, 3, "editing the composer must not cancel following");
      container.dispatchEvent(new PointerEvent("pointerdown", { button: 0 }));
      container.scrollTop = 400;
      container.dispatchEvent(new Event("scroll"));
      assert.equal(departures, 4);
      window.dispatchEvent(new PointerEvent("pointerup"));
      container.scrollTop = 300;
      container.dispatchEvent(new Event("scroll"));
      assert.equal(departures, 4);
      cleanup();
      container.dispatchEvent(Object.assign(new Event("wheel"), { deltaY: -10 }));
      assert.equal(departures, 4, "unmounted listeners do not retain the previous session");
    } finally { cleanup(); await view.cleanup(); }
  });
});
