/// <reference types="node" />

import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { StoryArchiveSurface } from "./StoryArchiveSurface";
import { createStoryBeat, createStoryDetails } from "./testFixtures";

describe("StoryArchiveSurface", () => {
  it("renders direct Story beats without Day, OC, or workspace semantics", () => {
    const markup = renderToStaticMarkup(<StoryArchiveSurface story={createStoryDetails()} busy={false} error="" onSubmitInput={async () => true} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-archive-surface"/);
    assert.match(markup, /剧情记录/);
    assert.match(markup, /你终于来了。/);
    assert.match(markup, /data-testid="story-current-time"/);
    assert.match(markup, /上午/);
    assert.match(markup, /aria-label="提交剧情输入"/);
    assert.doesNotMatch(markup, /Day|OC|world-workspace|属性|好感度/);
  });

  it("keeps the committed beat order from the Story repository", () => {
    const story = createStoryDetails({ beats: [createStoryBeat({ id: "first", sequence: 1 }), createStoryBeat({ id: "second", sequence: 2, text: "门开了。" })] });
    const markup = renderToStaticMarkup(<StoryArchiveSurface story={story} busy={false} error="" onSubmitInput={async () => true} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.ok(markup.indexOf("你终于来了。") < markup.indexOf("门开了。"));
  });
});
