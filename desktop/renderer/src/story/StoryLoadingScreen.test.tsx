/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryLoadingScreen } from "./StoryLoadingScreen";

describe("StoryLoadingScreen", () => {
  it("renders staged progress for initial Story entry", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="listing" />);
    assert.match(markup, /data-testid="story-loading-screen"/);
    assert.match(markup, /url\(\.\/assets\/backgrounds\/default-galgame-bg\.png\)/);
    assert.match(markup, />读取剧情</);
    assert.match(markup, />恢复进度</);
    assert.match(markup, />准备开场</);
    assert.doesNotMatch(markup, /spinner|animate-pulse/);
  });

  it("shows measured progress after a long load", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="story" elapsedMs={2_100} loaded={2} total={4} />);
    assert.match(markup, /role="progressbar"/);
    assert.match(markup, /aria-valuenow="2"/);
    assert.match(markup, /2 \/ 4/);
    assert.match(markup, /width:50%/);
  });
});
