/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mountTestComponent } from "./testing/domTestHarness";
import { CrossfadeLayers } from "./CrossfadeLayers";

const layers = (container: HTMLElement) => Array.from(container.querySelectorAll<HTMLElement>("[data-value]")).map((element) => ({
  value: element.dataset.value,
  className: element.parentElement?.className ?? "",
}));

const renderLayers = (value: string, resetKey: string) => (
  <CrossfadeLayers value={value} variant="focus" resetKey={resetKey} render={(url) => <img data-value={url} alt="" />} />
);

describe("CrossfadeLayers", () => {
  it("brings a new value of the same subject in with the focus crossfade", async () => {
    const view = await mountTestComponent(renderLayers("calm.png", "rin"));
    try {
      await view.render(renderLayers("happy.png", "rin"));
      const [outgoing, incoming] = layers(view.container);
      assert.equal(outgoing?.value, "calm.png");
      assert.match(outgoing!.className, /crossfade-out-focus/);
      assert.equal(incoming?.value, "happy.png");
      assert.match(incoming!.className, /crossfade-in-focus/);
    } finally {
      await view.cleanup();
    }
  });

  it("swaps outright when the subject changes (a role switch the view transition animates)", async () => {
    const view = await mountTestComponent(renderLayers("rin.png", "rin"));
    try {
      await view.render(renderLayers("natsu.png", "natsu"));
      const shown = layers(view.container);
      assert.deepEqual(shown.map((layer) => layer.value), ["natsu.png"]);
      assert.doesNotMatch(shown[0]!.className, /crossfade/);
    } finally {
      await view.cleanup();
    }
  });
});
