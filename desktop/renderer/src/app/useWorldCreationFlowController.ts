import { useCallback, useState } from "react";
import type { WorldBridgeClient } from "../world/bridgeClient";
import type { NativeIdentityDraft, WorldCreationInput } from "../world/types";
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

/** Owns draft preview and confirmation state for the World creation route. */
export function useWorldCreationFlowController({ client, controller, loadWorldForPlay, run }: Args) {
  const [seed, setSeed] = useState(createWorldSeed);
  const [draft, setDraft] = useState<Awaited<ReturnType<WorldBridgeClient["previewDraft"]>> | null>(null);

  const previewDraft = useCallback((input: WorldCreationInput) => {
    void run(() => client.previewDraft(input), setDraft);
  }, [client, run]);

  const confirmDraft = useCallback((draftId: string, identities: NativeIdentityDraft[]) => {
    void run(
      () => client.confirmDraft(draftId, identities),
      async (createdWorld) => {
        await controller.reloadWorlds();
        await loadWorldForPlay(createdWorld.id);
        setDraft(null);
      },
    );
  }, [client, controller, loadWorldForPlay, run]);

  return {
    seed,
    draft,
    resetDraft: () => setDraft(null),
    rerollSeed: () => {
      const nextSeed = createWorldSeed();
      setSeed(nextSeed);
      return nextSeed;
    },
    previewDraft,
    confirmDraft,
  };
}
