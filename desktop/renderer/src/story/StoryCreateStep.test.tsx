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
    assert.match(markup, /resize-none/);
    assert.match(markup, /overflow-hidden/);
    assert.doesNotMatch(markup, /resize-y/);
  });

  it("keeps the final player step focused and shows its inline summary", () => {
    const input = createInitialStoryCreationInput();
    input.title = "雨港";
    input.background = "潮汐带回名字";
    input.startsAt = "2026-08-02T10:00";
    input.playerProfile = { displayName: "岚", identity: "抄写员", appearance: "短发" };
    const markup = renderToStaticMarkup(<StoryCreateStep step="player" roles={[]} input={input} selectedRole={{ id: "role-1", name: "澪", description: "沉默的守灯人" }} reducedMotion onSelectRole={() => undefined} onChangeSetting={() => undefined} onChangeProfile={() => undefined} />);

    assert.match(markup, /data-testid="story-create-step"/);
    assert.match(markup, /aria-label="剧情摘要"/);
    assert.match(markup, /雨港/);
    assert.match(markup, /澪/);
    assert.match(markup, /玩家/);
  });
});
