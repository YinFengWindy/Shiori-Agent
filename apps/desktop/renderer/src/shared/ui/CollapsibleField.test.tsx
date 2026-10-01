import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/sdk/testing";
import { CollapsibleField } from "./CollapsibleField";

test("a field disclosure names its controlled region and removes the closed editor from focus order", async () => {
  let toggles = 0;
  const renderField = (expanded: boolean) => (
    <CollapsibleField title="设定" value={"第一行\n第二行"} expanded={expanded} onToggle={() => { toggles += 1; }}>
      <textarea aria-label="设定" defaultValue={"第一行\n第二行"} />
    </CollapsibleField>
  );
  const view = await mountTestComponent(renderField(false));
  try {
    const button = view.container.querySelector("button");
    assert.ok(button);
    assert.equal(button.type, "button");
    assert.equal(button.getAttribute("aria-expanded"), "false");
    const body = document.getElementById(button.getAttribute("aria-controls") ?? "");
    assert.ok(body);
    assert.equal(body.hidden, true);
    assert.equal(document.getElementById(body.getAttribute("aria-labelledby") ?? "")?.textContent, "设定");
    assert.equal(view.container.querySelector("textarea"), null);
    assert.equal(view.container.querySelector("p")?.textContent, "第一行 第二行");
    await act(async () => button.click());
    assert.equal(toggles, 1);

    await view.render(renderField(true));
    assert.equal(button.getAttribute("aria-expanded"), "true");
    assert.equal(body.hidden, false);
    assert.equal(view.container.querySelector("p"), null);
    assert.equal(view.container.querySelector("textarea")?.getAttribute("aria-label"), "设定");
  } finally { await view.cleanup(); }
});
