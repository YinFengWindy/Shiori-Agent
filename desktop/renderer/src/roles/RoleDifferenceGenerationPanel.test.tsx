import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { RoleDifferenceGenerationPanel } from "./RoleDifferenceGenerationPanel";
import { createRoleDifferenceGenerationState } from "./roleDifferenceGeneration";

describe("RoleDifferenceGenerationPanel", () => {
  it("requires a selected base image before enabling the magic-wand action", () => {
    const markup = renderToStaticMarkup(
      <RoleDifferenceGenerationPanel
        baseAssetPath=""
        bridgeReady
        state={createRoleDifferenceGenerationState()}
        onGenerate={() => undefined}
      />,
    );

    assert.match(markup, /aria-label="自动生成差分"/);
    assert.match(markup, /disabled/);
    assert.match(markup, /请先选择一张基准图/);
  });
});
