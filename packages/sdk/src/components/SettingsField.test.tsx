import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SettingsToggleField } from "./SettingsField";

test("a settings toggle row names its switch by the row label without narrating its state", () => {
  const markup = renderToStaticMarkup(<SettingsToggleField label="启用功能" checked onChange={() => undefined} />);
  assert.match(markup, /role="switch"/);
  assert.match(markup, /aria-checked="true"/);
  assert.match(markup, /aria-label="启用功能"/);
  assert.doesNotMatch(markup, /已启用|未启用/);
});
