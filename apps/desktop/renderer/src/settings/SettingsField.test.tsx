import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { SettingsField } from "./SettingsField";

describe("SettingsField", () => {
  it("centers rows without supporting text", () => {
    const markup = renderToStaticMarkup(
      <SettingsField label="API Key">
        <input />
      </SettingsField>,
    );

    assert.match(markup, /xl:items-center/);
    assert.doesNotMatch(markup, /xl:items-start/);
  });

  it("keeps rows with supporting text aligned to the top", () => {
    const markup = renderToStaticMarkup(
      <SettingsField label="API Key" hint="用于连接服务。">
        <input />
      </SettingsField>,
    );

    assert.match(markup, /xl:items-start/);
    assert.doesNotMatch(markup, /xl:items-center/);
  });
});
