import { useCallback } from "react";
import type { StoryBridgeClient } from "../story/storyBridgeClient";
import type { StoryCreationInput } from "../story/types";
import type { useStoryController } from "../story/useStoryController";
import type { RunStoryOperation } from "./useStoryPresentationOperation";

type Args = {
  client: StoryBridgeClient;
  controller: ReturnType<typeof useStoryController>;
  loadStoryForPlay: (storyId: string) => Promise<void>;
  run: RunStoryOperation;
};

/** Submits the Story form directly and opens the created Story. */
export function useStoryCreationFlowController({ client, controller, loadStoryForPlay, run }: Args) {
  const createStory = useCallback((input: StoryCreationInput, creationId: string) => {
    void run(
      () => client.createStory(input, creationId),
      async (createdStory) => {
        await controller.reloadStories();
        await loadStoryForPlay(createdStory.id);
      },
    );
  }, [client, controller, loadStoryForPlay, run]);

  return { createStory };
}
