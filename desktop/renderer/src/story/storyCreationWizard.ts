import type { StoryCreationInput } from "./types";

export const creationSteps = ["role", "setting", "player", "review"] as const;

export type CreationStep = (typeof creationSteps)[number];

/** Creates the local form state accepted by stories.create. */
export function createInitialStoryCreationInput(): StoryCreationInput {
  return {
    title: "",
    background: "",
    startsAt: "",
    roleId: "",
    playerProfile: { displayName: "", appearance: "", identity: "" },
  };
}

/** Reports whether the required input for one Story creation step is complete. */
export function isCreationStepComplete(step: CreationStep, input: StoryCreationInput): boolean {
  if (step === "role") return Boolean(input.roleId);
  if (step === "setting") return Boolean(input.title.trim() && input.background.trim() && input.startsAt.trim());
  if (step === "review") return Boolean(
    input.roleId
    && input.title.trim()
    && input.background.trim()
    && input.startsAt.trim()
    && input.playerProfile.displayName.trim()
    && input.playerProfile.identity.trim()
    && input.playerProfile.appearance.trim(),
  );
  return Boolean(
    input.playerProfile.displayName.trim()
    && input.playerProfile.identity.trim()
    && input.playerProfile.appearance.trim(),
  );
}
