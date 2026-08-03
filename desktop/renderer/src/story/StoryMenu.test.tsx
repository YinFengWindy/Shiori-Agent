/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryLoadList } from "./StoryMenu";
import { createStorySummary } from "./testFixtures";

describe("StoryLoadList", () => {
  it("renders as a full-screen Story surface", () => {
    const markup = renderToStaticMarkup(<StoryLoadList stories={[createStorySummary()]} busy={false} reducedMotion={false} onBack={() => undefined} onLoadStory={() => undefined} />);
    assert.match(markup, /data-testid="story-load"/);
    assert.match(markup, /data-testid="story-load-panel"/);
    assert.match(markup, />载入剧情</);
    assert.match(markup, /data-testid="story-load-list"/);
    assert.match(markup, /bg-\[#FFF8FC\]\/45/);
    assert.doesNotMatch(markup, /World|world/);
  });
});
