/// <reference types="node" />

import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { createWorldDetails } from "./testFixtures";
import { WorldGameInteraction } from "./WorldGameInteraction";

describe("WorldGameInteraction", () => {
  it("renders the dialogue gate text and an explicit reveal control", () => {
    const world = createWorldDetails();
    const markup = renderToStaticMarkup(
      <WorldGameInteraction
        world={world}
        beat={world.scene.beats[0]}
        paused={false}
        performing
        busy={false}
        dialogue={{ cueId: "cue-1", text: "你终于来了。", visibleText: "你终", speakerName: "凛", fullyRevealed: false, paused: false }}
        onContinueDialogue={() => undefined}
        onSubmitAction={async () => true}
        onAdvance={() => undefined}
        onResolveBarrier={() => undefined}
      />,
    );

    assert.match(markup, />你终</);
    assert.doesNotMatch(markup, />你终于来了。</);
    assert.match(markup, /aria-label="显示完整对话"/);
  });
});
