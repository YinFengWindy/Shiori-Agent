/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RoleMoodBindingsPanel } from "./RoleMoodBindingsPanel";

function renderRoleMoodBindingsPanel(): string {
  return renderToStaticMarkup(
    <RoleMoodBindingsPanel
      moodCatalog={["calm", "happy"]}
      defaultMood="calm"
      activeMood="calm"
      activeMoodIllustrationPath=""
      activeMoodIllustrationAbsPath=""
      selectedAssetPath="illustrations/mira-smile.png"
      onSelectMood={() => undefined}
      onBindSelectedAsset={() => undefined}
      onClearMoodBinding={() => undefined}
    />,
  );
}

describe("RoleMoodBindingsPanel", () => {
  it("renders content inside the shared role asset container without adding another full card shell", () => {
    const markup = renderRoleMoodBindingsPanel();

    assert.match(markup, /为当前角色的每个心情绑定一张差分立绘。/);
    assert.match(markup, /min-h-\[360px\]/);
    assert.doesNotMatch(markup, /min-h-\[420px\]/);
    assert.doesNotMatch(markup, /rounded-\[24px\]/);
    assert.doesNotMatch(markup, /border-\[#E4EAF0\]/);
  });
});
