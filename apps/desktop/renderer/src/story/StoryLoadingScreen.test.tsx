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
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="listing" phase="reading-list" />);
    assert.match(markup, /data-testid="story-loading-screen"/);
    assert.match(markup, /url\(\.\/assets\/backgrounds\/default-galgame-bg\.png\)/);
    assert.match(markup, /aria-label="Story menu loading"/);
    assert.match(markup, />Preparing</);
    assert.match(markup, />Read story list</);
    assert.match(markup, />Prepare menu</);
    assert.doesNotMatch(markup, />Complete</);
    assert.match(markup, /data-testid="story-loading-spinner"/);
    assert.match(markup, /animate-spin/);
    assert.doesNotMatch(markup, /Enter Story|Restore progress|Prepare stage/);
    assert.doesNotMatch(markup, /Story \/ Menu|Story \/ Loading/);
    assert.doesNotMatch(markup, /animate-pulse/);
    assert.doesNotMatch(markup, /[\u4e00-\u9fff]/);
  });

  it("shows measured progress after a long load", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="story" phase="preparing-opening" elapsedMs={2_100} loaded={2} total={4} />);
    assert.match(markup, /aria-label="Story loading"/);
    assert.match(markup, />Preparing</);
    assert.match(markup, />Prepare stage</);
    assert.match(markup, />Prepare stage</);
    assert.match(markup, /role="progressbar"/);
    assert.match(markup, /aria-valuenow="2"/);
    assert.match(markup, /2 \/ 4/);
    assert.match(markup, /width:50%/);
  });

  it("uses the resolved random backdrop and sampled menu theme", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen background={resolvedBackground} mode="listing" phase="preparing-menu" />);
    assert.match(markup, /url\(shiori-asset:\/\/local\/story-menu-random\.webp\)/);
    assert.match(markup, /hue-rotate\(18deg\) saturate\(1\.12\)/);
    assert.match(markup, /data-testid="story-loading-rail"/);
    assert.match(markup, /data-testid="story-loading-current-stage">Prepare menu/);
    assert.doesNotMatch(markup, /data-testid="story-menu-title"/);
  });

  it("checks every stage before leaving the loading transition", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="listing" phase="menu-ready" />);
    assert.match(markup, /data-testid="story-loading-current-stage">Story menu ready/);
    assert.match(markup, /Ready/);
    assert.doesNotMatch(markup, /story-loading-spinner/);
    assert.match(markup, /data-testid="story-loading-stage-0-check"/);
    assert.match(markup, /data-testid="story-loading-stage-1-check"/);
  });

  it("checks every gameplay stage before entering the Story", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="story" phase="opening-ready" />);
    assert.match(markup, /data-testid="story-loading-current-stage">Stage ready/);
    assert.match(markup, /data-testid="story-loading-stage-0-check"/);
    assert.match(markup, /data-testid="story-loading-stage-1-check"/);
    assert.match(markup, /data-testid="story-loading-stage-2-check"/);
    assert.doesNotMatch(markup, /story-loading-spinner/);
  });

  it("shows recovery commands when loading fails", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="story" phase="reading-story" error="读取失败" onRetry={() => undefined} onBack={() => undefined} />);
    assert.match(markup, /role="alert">读取失败/);
    assert.match(markup, />Back</);
    assert.match(markup, />Retry</);
  });
});
