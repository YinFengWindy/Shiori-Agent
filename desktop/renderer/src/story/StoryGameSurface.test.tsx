/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryGameSurface } from "./StoryGameSurface";
import { createStoryDetails } from "./testFixtures";

describe("StoryGameSurface", () => {
  it("renders the active Story as a visual-novel stage with dialogue and player input", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface story={createStoryDetails()} busy={false} error="" characterAvatarUrl="shiori-asset://local/role" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-surface"/);
    assert.match(markup, /url\(\.\/assets\/backgrounds\/default-galgame-bg\.png\)/);
    assert.match(markup, /shiori-asset:\/\/local\/role/);
    assert.match(markup, />你终于来了。</);
    assert.match(markup, /data-testid="story-current-time"/);
    assert.match(markup, />上午</);
    assert.match(markup, /aria-label="提交剧情行动"/);
    assert.match(markup, /aria-label="查看剧情记录"/);
  });

  it("uses the Story-owned background resource when it is ready", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface story={createStoryDetails({ backgroundResource: { id: "resource-1", storyId: "story-1", kind: "background", status: "ready", path: "D:\\stories\\opening.png", prompt: "anime screencap", sourceTurnId: "turn-1", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" } })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-backdrop"/);
    assert.match(markup, /shiori-asset:\/\/local\/unavailable/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });
});
