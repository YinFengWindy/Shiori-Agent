/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RoleMoodBindingsPanel } from "./RoleMoodBindingsPanel";

function renderRoleMoodBindingsPanel(): string {
  return renderToStaticMarkup(
    <RoleMoodBindingsPanel
      selectedAssetPath="illustrations/mira-smile.png"
      selectedAssetAbsPath="mira-asset://local?path=D%3A%5Cillustrations%5Cmira-smile.png"
      selectedMood="calm"
      onSaveMoodBinding={() => undefined}
    />,
  );
}

describe("RoleMoodBindingsPanel", () => {
  it("renders content inside the shared role asset container without adding another full card shell", () => {
    const markup = renderRoleMoodBindingsPanel();

    assert.match(markup, /对应心情/);
    assert.match(markup, /min-h-\[360px\]/);
    assert.doesNotMatch(markup, /min-h-\[420px\]/);
    assert.doesNotMatch(markup, /rounded-\[24px\]/);
    assert.doesNotMatch(markup, /border-\[#E4EAF0\]/);
    assert.doesNotMatch(markup, /先在左侧选中一张差分图/);
    assert.doesNotMatch(markup, /· 默认/);
    assert.doesNotMatch(markup, /当前选中素材：/);
    assert.doesNotMatch(markup, /清除当前映射/);
  });
});
