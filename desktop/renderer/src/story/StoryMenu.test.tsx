/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryLoadList } from "./StoryMenu";
import { createStorySummary } from "./testFixtures";

describe("StoryLoadList", () => {
  it("uses a Story album treatment instead of a World utility list", () => {
    const markup = renderToStaticMarkup(<StoryLoadList stories={[createStorySummary()]} busy={false} reducedMotion={false} onBack={() => undefined} onLoadStory={() => undefined} />);
    assert.match(markup, />STORY ALBUM</);
    assert.match(markup, /data-testid="story-load-list"/);
    assert.match(markup, /bg-\[#FFF8FC\]\/55/);
    assert.doesNotMatch(markup, /World|world/);
  });
});
