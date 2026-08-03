/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryAppSurface } from "./StoryAppSurface";

describe("StoryAppSurface", () => {
  it("owns a full-window surface without a shared navigation header", () => {
    const markup = renderToStaticMarkup(<StoryAppSurface><div>剧情内容</div></StoryAppSurface>);
    assert.match(markup, /story-app-surface/);
    assert.match(markup, /h-screen/);
    assert.doesNotMatch(markup, /返回 Shiori|grid-rows-\[48px/);
  });
});
