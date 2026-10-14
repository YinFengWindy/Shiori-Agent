import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { TaskOutput } from "./TaskOutput";

test("new output preserves the reading container and scroll until the user requests latest", async () => {
  const view = await mountTestComponent(<TaskOutput output={"old\n".repeat(200)} />);
  try {
    const output = view.container.querySelector("pre"); assert.ok(output);
    output.scrollTop = 120;
    Object.defineProperty(output, "scrollHeight", { configurable: true, value: 1000 });
    await view.render(<TaskOutput output={"old\n".repeat(200) + "new output"} />);
    assert.equal(view.container.querySelector("pre"), output);
    assert.equal(output.scrollTop, 120);
    const button = view.container.querySelector("button"); assert.ok(button);
    await act(async () => button.click());
    assert.equal(output.scrollTop, 1000);
    assert.equal(view.container.querySelector("button"), null);
  } finally { await view.cleanup(); }
});
