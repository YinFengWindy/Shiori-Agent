/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryLauncher } from "./StoryLauncher";
import { createStorySummary } from "./testFixtures";

const props = {
  onCreateStory: () => undefined,
  onLoadStory: () => undefined,
  onOpenSettings: () => undefined,
  onExit: () => undefined,
};

describe("StoryLauncher", () => {
  it("renders create, load, settings, and exit commands", () => {
    const markup = renderToStaticMarkup(<StoryLauncher stories={[createStorySummary()]} {...props} />);
    assert.ok(markup.includes("NEW STORY"));
    assert.ok(markup.includes("LOAD STORY"));
    assert.ok(markup.includes("SETTINGS"));
    assert.ok(markup.includes("EXIT"));
    assert.ok(markup.includes("栞 / SHIORI"));
    assert.ok(markup.includes("./assets/branding/shiori-title-logo.png"));
    assert.ok(markup.includes("url(./assets/backgrounds/default-galgame-bg.png)"));
    assert.doesNotMatch(markup, /创建世界|加载世界/);
  });

  it("keeps the Story album closed until load is selected", () => {
    const markup = renderToStaticMarkup(<StoryLauncher stories={[createStorySummary()]} {...props} />);
    assert.doesNotMatch(markup, /data-testid="story-load-list"/);
    assert.match(markup, />LOAD STORY</);
  });
});
