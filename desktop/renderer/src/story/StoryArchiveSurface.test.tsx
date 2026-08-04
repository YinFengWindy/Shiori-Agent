/// <reference types="node" />

import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { StoryArchiveSurface } from "./StoryArchiveSurface";
import { createStoryBeat, createStoryDetails } from "./testFixtures";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

const resolvedBackground: StoryMenuBackground = {
  url: "shiori-asset://local/story-menu-random.webp",
  theme: {
    commandFilter: "hue-rotate(18deg) saturate(1.12)",
    titleHighlight: "rgba(224,96,160,0.35)",
  },
};

describe("StoryArchiveSurface", () => {
  it("renders direct Story beats without Day, OC, or workspace semantics", () => {
    const markup = renderToStaticMarkup(<StoryArchiveSurface background={resolvedBackground} story={createStoryDetails()} error="" onReturnToGame={() => undefined} />);
    assert.match(markup, /data-testid="story-archive-surface"/);
    assert.match(markup, /data-testid="story-archive-backdrop"/);
    assert.match(markup, /url\(shiori-asset:\/\/local\/story-menu-random\.webp\)/);
    assert.match(markup, /剧情记录/);
    assert.match(markup, /你终于来了。/);
    assert.match(markup, /data-testid="story-current-time"/);
    assert.match(markup, /上午/);
    assert.match(markup, /aria-label="返回游戏页"/);
    assert.match(markup, /title="返回游戏页"/);
    assert.match(markup, /font-serif text-2xl font-semibold text-white/);
    assert.match(markup, /font-serif text-base leading-7 text-white/);
    assert.doesNotMatch(markup, /剧情设置|返回剧情列表/);
    assert.doesNotMatch(markup, /提交剧情输入|写下你的行动或回应/);
    assert.doesNotMatch(markup, /Day|OC|world-workspace|属性|好感度/);
  });

  it("keeps the committed beat order from the Story repository", () => {
    const story = createStoryDetails({ beats: [createStoryBeat({ id: "first", sequence: 1 }), createStoryBeat({ id: "second", sequence: 2, text: "门开了。" })] });
    const markup = renderToStaticMarkup(<StoryArchiveSurface story={story} error="" onReturnToGame={() => undefined} />);
    assert.ok(markup.indexOf("你终于来了。") < markup.indexOf("门开了。"));
  });
});
