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
      selectedAssetAbsPath="shiori-asset://local/shiori-smile-token"
      selectedMood="calm"
      onSaveMoodBinding={() => undefined}
      onClearSelectedAsset={() => undefined}
    />,
  );
}

describe("RoleMoodBindingsPanel", () => {
  it("renders the selected mood binding and accessible clear action", () => {
    const markup = renderRoleMoodBindingsPanel();

    assert.match(markup, /对应差分/);
    assert.match(markup, /aria-label="取消选中差分图"/);
    assert.doesNotMatch(markup, /先在左侧选中一张差分图/);
    assert.doesNotMatch(markup, /· 默认/);
    assert.doesNotMatch(markup, /当前选中素材：/);
    assert.doesNotMatch(markup, /清除当前映射/);
  });
});
