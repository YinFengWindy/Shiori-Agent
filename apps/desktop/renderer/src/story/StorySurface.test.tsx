/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { STORY_SURFACE_BACKDROP_FADE_SECONDS, STORY_SURFACE_BACKDROP_TRANSITION_SECONDS, StorySurface } from "./StorySurface";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

const resolvedBackground: StoryMenuBackground = {
  url: "shiori-asset://local/story-menu-random.webp",
  theme: {
    commandFilter: "hue-rotate(18deg) saturate(1.12)",
    titleHighlight: "rgba(224,96,160,0.35)",
  },
};

describe("StorySurface", () => {
  it("provides one shared Story backdrop and full-width panel shell", () => {
    const markup = renderToStaticMarkup(<StorySurface dataTestId="story-test" panelTestId="story-test-panel"><div>内容</div></StorySurface>);

    assert.match(markup, /data-testid="story-test"/);
    assert.match(markup, /data-testid="story-test-backdrop"/);
    assert.match(markup, /data-testid="story-test-panel"/);
    assert.match(markup, /min-h-full w-full/);
    assert.match(markup, /border-y border-\[#DDA9BE\]\/75/);
    assert.match(markup, /bg-\[#FFF8FC\]\/72/);
    assert.match(markup, /backdrop-blur-xl/);
    assert.match(markup, /backdrop-saturate-150/);
  });

  it("uses the resolved Story background instead of the bundled fallback", () => {
    const markup = renderToStaticMarkup(<StorySurface background={resolvedBackground} dataTestId="story-test" panelTestId="story-test-panel"><div>内容</div></StorySurface>);

    assert.match(markup, /url\(shiori-asset:\/\/local\/story-menu-random\.webp\)/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("keeps secondary-page backdrop entrance shorter than the launcher entrance", () => {
    assert.equal(STORY_SURFACE_BACKDROP_TRANSITION_SECONDS, 0.7);
  });

  it("leaves the shared background blur to the workspace backdrop", () => {
    const markup = renderToStaticMarkup(<StorySurface sharedBackdrop dataTestId="story-test" panelTestId="story-test-panel"><div>内容</div></StorySurface>);
    assert.doesNotMatch(markup, /backdrop-blur-xl/);
    assert.equal(STORY_SURFACE_BACKDROP_FADE_SECONDS, 0.7);
  });
});
