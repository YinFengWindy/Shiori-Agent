/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryCreateFlow } from "./StoryCreateFlow";

describe("StoryCreateFlow", () => {
  it("starts with a focused role-selection step", () => {
    const markup = renderToStaticMarkup(<StoryCreateFlow roles={[{ id: "role-1", name: "澪", description: "沉默的守灯人" }]} onBack={() => undefined} onCreate={() => undefined} />);
    assert.doesNotMatch(markup, /CREATE A STORY/);
    assert.match(markup, /bg-\[#FFF8FC\]/);
    assert.match(markup, /data-testid="story-create-flow-backdrop"/);
    assert.match(markup, /data-testid="story-create-panel"/);
    assert.doesNotMatch(markup, /01 \/ 03/);
    assert.doesNotMatch(markup, /<h2[^>]*>选择角色<\/h2>/);
    assert.match(markup, /aria-label="创建步骤"/);
    assert.match(markup, /aria-label="返回剧情主菜单"/);
    assert.match(markup, /data-testid="story-create-step"/);
    assert.match(markup, /border-0/);
    assert.match(markup, /aria-label="下一步"/);
    assert.match(markup, /title="下一步"/);
    assert.doesNotMatch(markup, /border-\[#B64B75\]\/55|border-\[#D5A9BB\]\/55/);
    assert.doesNotMatch(markup, /确认开始/);
    assert.doesNotMatch(markup, /inset-\[clamp\(12px,2vw,28px\)\]/);
    assert.doesNotMatch(markup, /grid-cols-\[220px/);
    assert.doesNotMatch(markup, /<aside/);
  });

  it("shows the first step action without a draft confirmation stage", () => {
    const markup = renderToStaticMarkup(<StoryCreateFlow roles={[]} onBack={() => undefined} onCreate={() => undefined} />);
    assert.match(markup, /aria-label="下一步"/);
    assert.doesNotMatch(markup, /草案|确认草案/);
  });
});
