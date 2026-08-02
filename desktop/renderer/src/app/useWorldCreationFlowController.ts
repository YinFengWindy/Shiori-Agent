import { useCallback, useState } from "react";
import type { WorldBridgeClient } from "../world/bridgeClient";
import type { WorldCreationInput } from "../world/types";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";
import type { RunWorldPresentation } from "./useWorldPresentationOperation";

type Args = {
  client: WorldBridgeClient;
  controller: ReturnType<typeof useWorldWorkspaceController>;
  loadWorldForPlay: (worldId: string) => Promise<void>;
  run: RunWorldPresentation;
};

function createWorldSeed(): string {
  return globalThis.crypto?.randomUUID?.() ?? `seed-${Date.now().toString(36)}`;
}

/** Owns the bridge-only draft lifecycle behind the Story creation route. */
export function useWorldCreationFlowController({ client, controller, loadWorldForPlay, run }: Args) {
  const [seed] = useState(createWorldSeed);

  const createStory = useCallback((input: WorldCreationInput) => {
    void run(
      async () => {
        const draft = await client.previewDraft(input);
        return client.confirmDraft(draft.id, draft.nativeIdentities);
      },
      async (createdWorld) => {
        await controller.reloadWorlds();
        await loadWorldForPlay(createdWorld.id);
      },
    );
  }, [client, controller, loadWorldForPlay, run]);

  return {
    seed,
    createStory,
  };
}
