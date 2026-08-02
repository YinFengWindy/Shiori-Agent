import type { WorldCreationInput } from "./types";

export const creationSteps = ["role", "setting", "player", "review"] as const;

export type CreationStep = (typeof creationSteps)[number];

/** Creates the locally held Story input before it is submitted through the bridge. */
export function createInitialWorldCreationInput(seed: string): WorldCreationInput {
  return {
    name: "",
    premise: "",
    rules: "",
    tone: "",
    selectedRoleIds: [],
    seed,
    firstOc: { name: "", identity: "", entryTime: "", entryLocation: "", primaryGoal: "" },
  };
}

/** Reports whether the required input for a creation step has been collected. */
export function isCreationStepComplete(step: CreationStep, input: WorldCreationInput): boolean {
  if (step === "role") return input.selectedRoleIds.length === 1;
  if (step === "setting") return Boolean(input.name.trim() && input.premise.trim());
  if (step === "player") {
    return Boolean(
      input.firstOc.name.trim()
      && input.firstOc.identity.trim()
      && input.firstOc.entryTime.trim()
      && input.firstOc.entryLocation.trim(),
    );
  }
  return creationSteps.slice(0, -1).every((requiredStep) => isCreationStepComplete(requiredStep, input));
}
