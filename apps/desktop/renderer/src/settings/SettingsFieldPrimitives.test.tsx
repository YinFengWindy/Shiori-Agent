/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import {
  SettingsSecretInput,
  SettingsToggleField,
} from "./SettingsFieldPrimitives.js";

describe("SettingsFieldPrimitives", () => {
  it("renders secrets hidden and toggles with accessible state", () => {
    const secretMarkup = renderToStaticMarkup(
      <SettingsSecretInput value="secret-value" onChange={() => undefined} />,
    );
    const toggleMarkup = renderToStaticMarkup(
      <SettingsToggleField label="启用功能" checked onChange={() => undefined} />,
    );

    assert.match(secretMarkup, /type="password"/);
    assert.match(secretMarkup, /value="secret-value"/);
    assert.match(toggleMarkup, /role="switch"/);
    assert.match(toggleMarkup, /aria-checked="true"/);
    assert.match(toggleMarkup, /aria-label="启用功能"/);
  });
});
