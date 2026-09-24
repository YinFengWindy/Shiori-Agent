import type { ModelRegistrationFormData } from "../../../src/bridge/shared";

type ModelEffortValue = ModelRegistrationFormData["effort"];

/**
 * The one Chinese vocabulary for reasoning effort, shared by the chat model
 * menu, settings and onboarding so the same value never reads two ways.
 */
export const modelEffortLabels: Record<ModelEffortValue, string> = {
  none: "关闭",
  low: "低",
  high: "高",
  max: "最高",
};

/** Effort values in ascending order with their labels, for segmented controls and selects. */
export const modelEffortOptions: ReadonlyArray<{ value: ModelEffortValue; label: string }> = (
  ["none", "low", "high", "max"] as const
).map((value) => ({ value, label: modelEffortLabels[value] }));
