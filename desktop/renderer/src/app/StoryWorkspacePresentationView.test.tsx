/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { StoryPresentationMode } from "./storyPresentationModes";
import { StoryWorkspacePresentationView, type StoryCreationPresentationController, type StoryOperationPresentationController, type StoryWorkspacePresentationController } from "./StoryWorkspacePresentationView";
import { createStoryDetails, createStorySummary } from "../story/testFixtures";

const story = createStoryDetails();

const controller: StoryWorkspacePresentationController = {
  story,
  stories: [createStorySummary()],
  loading: false,
  error: "",
  busy: false,
  reloadStories: async () => undefined,
  submitInput: async () => true,
};

const operation: StoryOperationPresentationController = { error: "", busy: false, clearError: () => undefined };
const creation: StoryCreationPresentationController = { createStory: () => undefined };

function render(mode: StoryPresentationMode) {
  return renderToStaticMarkup(<StoryWorkspacePresentationView roles={[]} mode={mode} loadingStoryId="" loadingElapsedMs={0} cgGallery={[]} cgGalleryLoading={false} controller={controller} operation={operation} creation={creation} setMode={() => undefined} loadStoryForPlay={async () => undefined} onOpenCg={() => undefined} onRetryCg={() => undefined} onOpenSettings={() => undefined} onCloseSettings={() => undefined} onExit={() => undefined} />);
}

describe("StoryWorkspacePresentationView", () => {
  it("uses the visual-novel stage for an active Story", () => {
    const markup = render("game");
    assert.match(markup, /data-testid="story-game-surface"/);
    assert.doesNotMatch(markup, /world-day-surface|world-workspace/);
  });

  it("uses the direct Story archive for history", () => {
    const markup = render("archive");
    assert.match(markup, /data-testid="story-archive-surface"/);
  });

  it("uses a full-screen Story surface for saved Stories", () => {
    const markup = render("load");
    assert.match(markup, /data-testid="story-load"/);
    assert.match(markup, /data-testid="story-load-panel"/);
    assert.match(markup, /data-testid="story-load-list"/);
  });
});
