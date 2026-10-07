/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SettingsSecretInput } from "./SettingsFieldPrimitives.js";

describe("SettingsFieldPrimitives", () => {
  it("renders secrets hidden", () => {
    const secretMarkup = renderToStaticMarkup(
      <SettingsSecretInput value="secret-value" onChange={() => undefined} />,
    );

    assert.match(secretMarkup, /type="password"/);
    assert.match(secretMarkup, /value="secret-value"/);
  });
});

it("SettingsNumberInput accepts a decimal ratio typed from an empty box", async () => {
  const { mountTestComponent, changeInputValue } = await import("@yinfengwindy/shiori-sdk/testing");
  const { SettingsNumberInput } = await import("./SettingsFieldPrimitives.js");
  const state = { value: 0.75 };
  const view = await mountTestComponent(null);
  const render = () => view.render(<SettingsNumberInput ariaLabel="触发比例" value={state.value} onChange={(value) => { state.value = value; void render(); }} />);
  try {
    await render();
    const input = view.container.querySelector("input");
    assert.ok(input);
    await changeInputValue(input, "");
    assert.equal(input.value, "");
    assert.equal(state.value, 0.75, "an empty box must not report 0");
    await act(async () => { input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })); });
    assert.equal(input.value, "0.75");
    for (const typed of ["", "0", "0.", "0.8"]) {
      await changeInputValue(input, typed);
      assert.equal(input.value, typed);
    }
    assert.equal(state.value, 0.8);
  } finally { await view.cleanup(); }
});
