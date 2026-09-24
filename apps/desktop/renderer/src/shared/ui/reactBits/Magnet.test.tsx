import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../../testing/domTestHarness";
import { getMagnetOffset, Magnet } from "./Magnet";

const rect = { left: 100, top: 100, width: 40, height: 40 };

describe("getMagnetOffset", () => {
  it("pulls toward the pointer inside the padded range", () => {
    assert.deepEqual(getMagnetOffset({ clientX: 150, clientY: 120 }, rect, 20, 10), { x: 3, y: 0 });
  });

  it("rests at the origin outside the padded range", () => {
    assert.deepEqual(getMagnetOffset({ clientX: 400, clientY: 400 }, rect, 20, 10), { x: 0, y: 0 });
  });
});

describe("Magnet", () => {
  it("moves its content without re-rendering and ignores moves that keep it at rest", async () => {
    let renders = 0;
    function Probe() {
      renders += 1;
      return <button type="button">save</button>;
    }
    const view = await mountTestComponent(<Magnet padding={20} strength={10}><Probe /></Magnet>);
    try {
      const outer = view.container.firstElementChild as HTMLDivElement;
      const inner = outer.firstElementChild as HTMLDivElement;
      outer.getBoundingClientRect = () => ({ ...rect, x: rect.left, y: rect.top, right: 140, bottom: 140, toJSON: () => ({}) });
      const move = (clientX: number, clientY: number) => act(async () => {
        window.dispatchEvent(new MouseEvent("mousemove", { clientX, clientY }));
      });

      await move(150, 120);
      assert.equal(inner.style.transform, "translate3d(3px, 0px, 0)");
      await move(400, 400);
      assert.equal(inner.style.transform, "translate3d(0px, 0px, 0)");

      // Already at rest: further far-away moves must not write the style again.
      inner.style.transform = "sentinel";
      await move(500, 500);
      await move(600, 20);
      assert.equal(inner.style.transform, "sentinel");
      assert.equal(renders, 1);
    } finally { await view.cleanup(); }
  });
});
