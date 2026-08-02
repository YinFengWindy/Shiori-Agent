/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { WorldPresentationMode } from "./worldPresentationModes";
import {
  WorldWorkspacePresentationView,
  type StoryCreationPresentationController,
  type StoryOperationPresentationController,
  type StoryWorkspacePresentationController,
} from "./WorldWorkspacePresentationView";
import { createWorldDetails } from "../world/testFixtures";

const world = createWorldDetails();

const controller: StoryWorkspacePresentationController = {
  world,
  worlds: [],
  loading: false,
  error: "",
  busy: false,
  reloadWorlds: async () => undefined,
  completeDay: async () => true,
};

const operation: StoryOperationPresentationController = {
  error: "",
  busy: false,
  clearError: () => undefined,
};

const creation: StoryCreationPresentationController = {
  seed: "seed",
  createStory: () => undefined,
};

function render(mode: WorldPresentationMode) {
  return renderToStaticMarkup(
    <WorldWorkspacePresentationView
      roles={[]}
      mode={mode}
      loadingWorldId=""
      loadingElapsedMs={0}
      controller={controller}
      operation={operation}
      creation={creation}
      setMode={() => undefined}
      loadWorldForPlay={async () => undefined}
      onOpenSettings={() => undefined}
      onCloseSettings={() => undefined}
      onExit={() => undefined}
    />,
  );
}

describe("WorldWorkspacePresentationView", () => {
  it("uses the Galgame stage for an active Story", () => {
    const markup = render("game");

    assert.match(markup, /data-testid="story-game-surface"/);
    assert.doesNotMatch(markup, /data-testid="world-day-surface"/);
  });

  it("keeps the Day surface for the optional story archive", () => {
    const markup = render("day");

    assert.match(markup, /data-testid="world-day-surface"/);
  });
});
