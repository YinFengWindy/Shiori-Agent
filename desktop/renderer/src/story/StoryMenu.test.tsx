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
    assert.doesNotMatch(markup, />LOAD STORY</);
    assert.match(markup, /data-testid="story-load-list"/);
    assert.match(markup, />2026年8月2日 · 上午 · 默认场景</);
    assert.doesNotMatch(markup, />上午</);
    assert.doesNotMatch(markup, /2026-08-02T10:00:00\+08:00/);
    assert.match(markup, /bg-\[#FFF8FC\]\/45/);
    assert.doesNotMatch(markup, /bg-\[#FFF8FC\]\/55/);
    assert.doesNotMatch(markup, /World|world/);
  });
});
