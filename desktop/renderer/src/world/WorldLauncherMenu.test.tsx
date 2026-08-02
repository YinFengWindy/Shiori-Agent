/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryLoadList } from "./WorldLauncherMenu";
import { createWorldSummary } from "./testFixtures";

describe("StoryLoadList", () => {
  it("uses a romance-story album treatment instead of a utility list", () => {
    const markup = renderToStaticMarkup(
      <StoryLoadList
        worlds={[createWorldSummary()]}
        busy={false}
        reducedMotion={false}
        onBack={() => undefined}
        onLoadWorld={() => undefined}
      />
    );

    assert.match(markup, />STORY ALBUM</);
    assert.match(markup, /border-b/);
    assert.match(markup, /bg-\[#FFF8FC\]\/55/);
    assert.doesNotMatch(markup, /border-l-2/);
  });
});
