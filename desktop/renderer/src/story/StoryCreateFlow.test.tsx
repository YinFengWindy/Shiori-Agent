/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryCreateFlow } from "./StoryCreateFlow";

describe("StoryCreateFlow", () => {
  it("starts with a focused role-selection step", () => {
    const markup = renderToStaticMarkup(<StoryCreateFlow roles={[{ id: "role-1", name: "澪", description: "沉默的守灯人" }]} onBack={() => undefined} onCreate={() => undefined} />);
    assert.match(markup, />CREATE A STORY</);
    assert.match(markup, /bg-\[#FFF8FC\]/);
    assert.match(markup, />选择角色</);
    assert.match(markup, /01 \/ 03/);
    assert.match(markup, /aria-label="创建步骤"/);
    assert.match(markup, /aria-label="返回剧情主菜单"/);
    assert.match(markup, /data-testid="story-create-step"/);
    assert.doesNotMatch(markup, /确认开始/);
    assert.doesNotMatch(markup, /grid-cols-\[220px/);
    assert.doesNotMatch(markup, /<aside/);
  });

  it("shows the first step action without a draft confirmation stage", () => {
    const markup = renderToStaticMarkup(<StoryCreateFlow roles={[]} onBack={() => undefined} onCreate={() => undefined} />);
    assert.match(markup, />下一步</);
    assert.doesNotMatch(markup, /草案|确认草案/);
  });
});
