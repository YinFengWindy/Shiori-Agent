import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import { Reveal } from "./Reveal";

test("a hidden block keeps its last content, inert, while it collapses and drops it once collapsed", async () => {
  const view = await mountTestComponent(<Reveal show={false}><p>二维码</p></Reveal>);
  const wrapper = () => view.container.firstElementChild as HTMLElement;
  try {
    // Starting hidden renders no content at all.
    assert.equal(view.container.textContent, "");
    assert.equal(wrapper().className, "reveal");
    await view.render(<Reveal show><p>二维码</p></Reveal>);
    assert.equal(wrapper().className, "reveal reveal-open");
    assert.equal(view.container.textContent, "二维码");
    await view.render(<Reveal show={false}>{null}</Reveal>);
    assert.equal(view.container.textContent, "二维码");
    assert.ok(wrapper().firstElementChild?.hasAttribute("inert"));
    await act(async () => wrapper().dispatchEvent(new Event("transitionend", { bubbles: true })));
    assert.equal(view.container.textContent, "");
  } finally { await view.cleanup(); }
});
