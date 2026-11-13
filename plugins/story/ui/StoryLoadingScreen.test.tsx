import { STORY_MENU_BACKGROUND_URL } from "./storyStaticAssets";
/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderStoryMarkup as renderToStaticMarkup } from "./testFixtures";
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
    assert.ok(markup.includes(`url(${STORY_MENU_BACKGROUND_URL})`));
    assert.match(markup, /aria-label="正在载入故事菜单"/);
    assert.match(markup, />准备中</);
    assert.match(markup, />读取剧情列表</);
    assert.match(markup, />准备菜单</);
    assert.doesNotMatch(markup, />完成</);
    assert.match(markup, /data-testid="story-loading-spinner"/);
    assert.match(markup, /animate-spin/);
    assert.doesNotMatch(markup, /恢复进度|布置舞台/);
    assert.doesNotMatch(markup, /Story \/ Menu|Story \/ Loading/);
    assert.doesNotMatch(markup, /animate-pulse/);
  });

  it("shows measured progress after a long load", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="story" phase="preparing-opening" elapsedMs={2_100} loaded={2} total={4} />);
    assert.match(markup, /aria-label="正在载入剧情"/);
    assert.match(markup, />准备中</);
    assert.match(markup, />布置舞台</);
    assert.match(markup, />布置舞台</);
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
    assert.match(markup, /data-testid="story-loading-current-stage">准备菜单/);
    assert.doesNotMatch(markup, /data-testid="story-menu-title"/);
  });

  it("checks every stage before leaving the loading transition", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="listing" phase="menu-ready" />);
    assert.match(markup, /data-testid="story-loading-current-stage">菜单已就绪/);
    assert.match(markup, /就绪/);
    assert.doesNotMatch(markup, /story-loading-spinner/);
    assert.match(markup, /data-testid="story-loading-stage-0-check"/);
    assert.match(markup, /data-testid="story-loading-stage-1-check"/);
  });

  it("checks every gameplay stage before entering the Story", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="story" phase="opening-ready" />);
    assert.match(markup, /data-testid="story-loading-current-stage">舞台已就绪/);
    assert.match(markup, /data-testid="story-loading-stage-0-check"/);
    assert.match(markup, /data-testid="story-loading-stage-1-check"/);
    assert.match(markup, /data-testid="story-loading-stage-2-check"/);
    assert.doesNotMatch(markup, /story-loading-spinner/);
  });

  it("shows recovery commands when loading fails", () => {
    const markup = renderToStaticMarkup(<StoryLoadingScreen mode="story" phase="reading-story" error="读取失败" onRetry={() => undefined} onBack={() => undefined} />);
    assert.match(markup, /role="alert"/);
    assert.match(markup, />返回</);
    assert.match(markup, />重试</);
  });
});
