/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RoleMoodBindingsPanel } from "./RoleMoodBindingsPanel";

function render(selectedAssetPath: string): string {
  return renderToStaticMarkup(
    <RoleMoodBindingsPanel selectedAssetPath={selectedAssetPath} selectedMood="calm" onSaveMoodBinding={() => undefined} />,
  );
}

describe("RoleMoodBindingsPanel", () => {
  it("edits the mood bound to the previewed image", () => {
    const markup = render("illustrations/mira-smile.png");

    assert.match(markup, /对应心情/);
    assert.match(markup, /value="calm"/);
    assert.doesNotMatch(markup, /disabled/);
  });

  it("stays off until an image is chosen", () => {
    assert.match(render(""), /disabled=""/);
  });
});
