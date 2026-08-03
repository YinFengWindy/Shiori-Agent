/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryLoadingScreen } from "./StoryLoadingScreen";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

const resolvedBackground: StoryMenuBackground = {
  url: "shiori-asset://local/story-menu-random.webp",
  theme: {
    commandFilter: "hue-rotate(18deg) saturate(1.12)",
    titleHighlight: "rgba(224,96,160,0.35)",
  },
};

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

  it("uses the resolved random backdrop and sampled menu theme", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen background={resolvedBackground} mode="listing" />);
    assert.match(markup, /url\(shiori-asset:\/\/local\/story-menu-random\.webp\)/);
    assert.match(markup, /hue-rotate\(18deg\) saturate\(1\.12\)/);
    assert.match(markup, /data-testid="story-loading-rail"/);
  });
});
