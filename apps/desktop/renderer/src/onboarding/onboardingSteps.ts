import type { OnboardingProgress } from "./onboardingState";
import type { OnboardingScene } from "./onboardingScript";

type OnboardingStepId = OnboardingProgress["step"];

/** Where one step stands in the progress indicator. */
export type OnboardingStepStatus = "done" | "current" | "upcoming";

/** The three setup steps in order, with their indicator labels. */
export const onboardingSteps: ReadonlyArray<{ id: OnboardingStepId; label: string }> = [
  { id: "model", label: "模型" },
  { id: "role", label: "角色" },
  { id: "workspace", label: "开始" },
];

/** Every step with its status; before the first read nothing is current. */
export function selectOnboardingStepStatuses(step: OnboardingStepId | undefined) {
  const current = onboardingSteps.findIndex((item) => item.id === step);
  return onboardingSteps.map((item, index) => {
    const status: OnboardingStepStatus = current < 0 || index > current ? "upcoming" : index < current ? "done" : "current";
    return { ...item, status };
  });
}

/**
 * Which scene the guide shows. A failure without data means the bridge could
 * not be read; with data it is a failed action (entering the workspace).
 */
export function selectOnboardingScene({ error, hasData, step }: { error: string; hasData: boolean; step: OnboardingStepId | undefined }): OnboardingScene {
  if (error) return hasData ? "failed" : "offline";
  return step ?? "loading";
}

/** Skipping only dismisses setup that is still to be done; the last step has nothing left to skip. */
export function canSkipOnboardingStep(step: OnboardingStepId | undefined) {
  return step === "model" || step === "role";
}
