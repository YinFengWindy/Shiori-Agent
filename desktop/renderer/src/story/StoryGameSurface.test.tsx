/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryGameSurface } from "./StoryGameSurface";
import { createStoryDetails } from "./testFixtures";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

const resolvedBackground: StoryMenuBackground = {
  url: "shiori-asset://local/story-menu-random.webp",
  theme: {
    commandFilter: "hue-rotate(18deg) saturate(1.12)",
    titleHighlight: "rgba(224,96,160,0.35)",
  },
};

describe("StoryGameSurface", () => {
  it("renders the active Story as a visual-novel stage with dialogue and player input", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface story={createStoryDetails()} busy={false} error="" characterAvatarUrl="shiori-asset://local/role" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-surface"/);
    assert.match(markup, /url\(\.\/assets\/backgrounds\/default-galgame-bg\.png\)/);
    assert.match(markup, />你终于来了。</);
    assert.match(markup, /data-testid="story-current-time"/);
    assert.match(markup, />上午</);
    assert.match(markup, /aria-label="提交剧情行动"/);
    assert.match(markup, /aria-label="查看剧情记录"/);
    assert.match(markup, /data-testid="story-dialogue-panel"/);
    assert.match(markup, /data-testid="story-dialogue-text"/);
    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
  });

  it("uses the Story-owned background resource when it is ready", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({ backgroundResource: { id: "resource-1", storyId: "story-1", kind: "background", status: "ready", path: "D:\\stories\\opening.png", prompt: "anime screencap", sourceTurnId: "turn-1", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" } })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-backdrop"/);
    assert.match(markup, /shiori-asset:\/\/local\/unavailable/);
    assert.match(markup, /data-testid="story-game-character"/);
    assert.match(markup, /shiori-asset:\/\/local\/role/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("falls back to the shared Story background when no Story CG is ready", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface background={resolvedBackground} story={createStoryDetails()} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /url\(shiori-asset:\/\/local\/story-menu-random\.webp\)/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });
});
