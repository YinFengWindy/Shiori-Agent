/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryGameSurface } from "./StoryGameSurface";
import { createWorldDetails } from "./testFixtures";

describe("StoryGameSurface", () => {
  it("renders the active Story as a visual-novel stage with dialogue and player input", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface world={createWorldDetails()} busy={false} error="" characterAvatarUrl="shiori-asset://local/role" onSubmitAction={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /data-testid="story-game-surface"/);
    assert.match(markup, /url\(\.\/assets\/backgrounds\/default-galgame-bg\.png\)/);
    assert.match(markup, /shiori-asset:\/\/local\/role/);
    assert.match(markup, />你终于来了。</);
    assert.match(markup, /aria-label="提交剧情行动"/);
    assert.match(markup, /aria-label="查看剧情记录"/);
  });
});
