/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { StoryPresentationMode } from "./storyPresentationModes";
import { STORY_PRESENTATION_TRANSITION_SECONDS, StoryWorkspacePresentationView, type StoryCreationPresentationController, type StoryOperationPresentationController, type StoryWorkspacePresentationController } from "./StoryWorkspacePresentationView";
import { createStoryDetails, createStorySummary } from "../story/testFixtures";

const story = createStoryDetails();

const controller: StoryWorkspacePresentationController = {
  story,
  stories: [createStorySummary()],
  loading: false,
  loadingPhase: "reading-list",
  error: "",
  busy: false,
  reloadStories: async () => undefined,
  submitInput: async () => true,
  regenerateCg: async () => true,
};

const operation: StoryOperationPresentationController = { error: "", busy: false, clearError: () => undefined };
const creation: StoryCreationPresentationController = { createStory: () => undefined };

function render(mode: StoryPresentationMode, loading = controller.loading) {
  return renderToStaticMarkup(<StoryWorkspacePresentationView roles={[]} mode={mode} loadingStoryId="" loadingElapsedMs={0} loadingPhase="reading-story" cgGallery={[]} cgGalleryLoading={false} controller={{ ...controller, loading }} operation={operation} creation={creation} setMode={() => undefined} loadStoryForPlay={async () => undefined} onOpenCg={() => undefined} onRetryCg={() => undefined} onOpenSettings={() => undefined} onCloseSettings={() => undefined} onExit={() => undefined} />);
}

describe("StoryWorkspacePresentationView", () => {
  it("uses the visual-novel stage for an active Story", () => {
    const markup = render("game");
    assert.match(markup, /data-testid="story-workspace-backdrop"/);
    assert.match(markup, /data-blur-mode="none" data-testid="story-workspace-backdrop-blur"/);
    assert.match(markup, /data-testid="story-game-surface"/);
    assert.match(markup, /data-testid="story-presentation-content" data-story-mode="game"/);
    assert.match(markup, /data-testid="story-game-backdrop"/);
    assert.ok(markup.indexOf("story-workspace-backdrop") < markup.indexOf("story-game-surface"));
    assert.doesNotMatch(markup, /world-day-surface|world-workspace/);
  });

  it("keeps the launcher command rail entrance when Story mode first opens", () => {
    const markup = render("launcher");
    assert.match(markup, /data-testid="story-launcher-command-rail"/);
    assert.match(markup, /opacity:0;transform:translateX\(28px\)/);
  });

  it("uses the direct Story archive for history", () => {
    const markup = render("archive");
    assert.match(markup, /data-testid="story-archive-surface"/);
    assert.doesNotMatch(markup, /data-testid="story-archive-backdrop"/);
  });

  it("uses a full-screen Story surface for saved Stories", () => {
    const markup = render("load");
    assert.match(markup, /data-blur-mode="surface" data-testid="story-workspace-backdrop-blur"/);
    assert.match(markup, /data-testid="story-load"/);
    assert.match(markup, /data-testid="story-presentation-content" data-story-mode="load"/);
    assert.match(markup, /data-testid="story-load-panel"/);
    assert.match(markup, /data-testid="story-load-list"/);
  });

  it("uses a shared transition for loading and the active Story stage", () => {
    assert.equal(STORY_PRESENTATION_TRANSITION_SECONDS, 0.42);
  });

  it("keeps a distinct transition when the launcher loading screen resolves", () => {
    const loadingMarkup = render("launcher", true);
    const launcherMarkup = render("launcher", false);
    assert.match(loadingMarkup, /data-story-transition-key="launcher-loading"/);
    assert.match(launcherMarkup, /data-story-transition-key="launcher"/);
  });

  it("keeps a failed Story list on the retryable loading surface", () => {
    const markup = renderToStaticMarkup(<StoryWorkspacePresentationView roles={[]} mode="launcher" loadingStoryId="" loadingElapsedMs={0} loadingPhase="reading-story" cgGallery={[]} cgGalleryLoading={false} controller={{ ...controller, story: null, loading: true, error: "读取失败" }} operation={operation} creation={creation} setMode={() => undefined} loadStoryForPlay={async () => undefined} onOpenCg={() => undefined} onRetryCg={() => undefined} onOpenSettings={() => undefined} onCloseSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /role="alert">读取失败/);
    assert.match(markup, />Retry</);
  });
});
