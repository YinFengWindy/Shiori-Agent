/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryCreateStep } from "./StoryCreateStep";
import { createInitialStoryCreationInput } from "./storyCreationWizard";

describe("StoryCreateStep", () => {
  it("auto-grows the opening background field without a resize handle", () => {
    const input = createInitialStoryCreationInput();
    const markup = renderToStaticMarkup(<StoryCreateStep step="setting" roles={[]} input={input} reducedMotion onSelectRole={() => undefined} onChangeSetting={() => undefined} onChangeProfile={() => undefined} />);

    assert.match(markup, /开场背景/);
    assert.match(markup, /开始时段/);
    assert.match(markup, /开始日期/);
    assert.match(markup, /清晨/);
    assert.match(markup, /上午/);
    assert.match(markup, /下午/);
    assert.match(markup, /夜晚/);
    assert.match(markup, /深夜/);
    assert.match(markup, /type="date"/);
    assert.doesNotMatch(markup, /datetime-local/);
    assert.doesNotMatch(markup, /北京时间/);
    assert.match(markup, /resize-none/);
    assert.match(markup, /overflow-hidden/);
    assert.doesNotMatch(markup, /resize-y/);
  });

  it("keeps the player step focused without showing the review", () => {
    const input = createInitialStoryCreationInput();
    input.title = "雨港";
    input.background = "潮汐带回名字";
    input.storyDate = "2026-08-01";
    input.timeBand = "上午";
    input.playerProfile = { displayName: "岚", identity: "抄写员", appearance: "短发" };
    const markup = renderToStaticMarkup(<StoryCreateStep step="player" roles={[]} input={input} selectedRole={{ id: "role-1", name: "澪", description: "沉默的守灯人" }} reducedMotion onSelectRole={() => undefined} onChangeSetting={() => undefined} onChangeProfile={() => undefined} />);

    assert.match(markup, /data-testid="story-create-step"/);
    assert.match(markup, /名称/);
    assert.doesNotMatch(markup, /aria-label="剧情总览"/);
    assert.doesNotMatch(markup, /剧情摘要|雨港|澪/);
  });

  it("shows the completed creation review as its own step", () => {
    const input = createInitialStoryCreationInput();
    input.roleId = "role-1";
    input.title = "雨港";
    input.background = "潮汐带回名字";
    input.storyDate = "2026-08-01";
    input.timeBand = "上午";
    input.playerProfile = { displayName: "岚", identity: "抄写员", appearance: "短发" };
    const markup = renderToStaticMarkup(<StoryCreateStep step="review" roles={[]} input={input} selectedRole={{ id: "role-1", name: "澪", description: "沉默的守灯人" }} reducedMotion onSelectRole={() => undefined} onChangeSetting={() => undefined} onChangeProfile={() => undefined} />);

    assert.match(markup, /aria-label="剧情总览"/);
    assert.match(markup, /雨港/);
    assert.match(markup, /潮汐带回名字/);
    assert.match(markup, /澪/);
    assert.match(markup, /岚/);
  });
});
