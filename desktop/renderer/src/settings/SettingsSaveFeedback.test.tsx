/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SettingsSaveFeedback } from "./SettingsSaveFeedback.js";

describe("SettingsSaveFeedback", () => {
  it("renders only terminal save feedback", () => {
    const savedMarkup = renderToStaticMarkup(
      <SettingsSaveFeedback phase="saved" message="配置已保存" />,
    );
    const savingMarkup = renderToStaticMarkup(
      <SettingsSaveFeedback phase="saving" message="正在保存" />,
    );

    assert.match(savedMarkup, /role="status"/);
    assert.match(savedMarkup, /配置已保存/);
    assert.equal(savingMarkup, "");
  });
});
