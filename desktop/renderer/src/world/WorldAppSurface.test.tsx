/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { WorldAppSurface } from "./WorldAppSurface";

describe("WorldAppSurface", () => {
  it("owns a full-window surface without a shared navigation header", () => {
    const markup = renderToStaticMarkup(<WorldAppSurface><div>世界内容</div></WorldAppSurface>);

    assert.match(markup, /world-app-surface/);
    assert.match(markup, /h-screen/);
    assert.doesNotMatch(markup, /返回 Shiori|grid-rows-\[48px/);
  });
});
