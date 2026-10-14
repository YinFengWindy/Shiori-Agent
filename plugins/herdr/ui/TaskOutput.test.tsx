import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { TaskOutput } from "./TaskOutput";

test("a replacement output window preserves displayed text and scroll until the user requests latest", async () => {
  const oldWindow = Array.from({ length: 100 }, (_, index) => `line ${index + 1}`).join("\n");
  const newWindow = Array.from({ length: 100 }, (_, index) => `line ${index + 101}`).join("\n");
  const view = await mountTestComponent(<TaskOutput output={oldWindow} />);
  try {
    const output = view.container.querySelector("pre"); assert.ok(output);
    output.scrollTop = 120;
    Object.defineProperty(output, "scrollHeight", { configurable: true, get: () => output.textContent === newWindow ? 2000 : 1000 });
    await view.render(<TaskOutput output={newWindow} />);
    assert.equal(view.container.querySelector("pre"), output);
    assert.equal(output.textContent, oldWindow);
    assert.equal(output.scrollTop, 120);
    const button = view.container.querySelector("button"); assert.ok(button);
    await act(async () => button.click());
    assert.equal(output.textContent, newWindow);
    assert.equal(output.scrollTop, 2000);
    assert.equal(view.container.querySelector("button"), null);
  } finally { await view.cleanup(); }
});
