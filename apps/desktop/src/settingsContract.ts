import type { ModelRegistrationFormData } from "./bridge/shared.js";

/** Defaults shared by the desktop settings reader and writer. */
export const desktopSettingsDefaults = Object.freeze({
  asrProvider: "tencent",
  asrBaseUrl: "https://asr.tencentcloudapi.com/",
  ttsProvider: "minimax",
  ttsBaseUrl: "https://api.minimaxi.com/v1/t2a_v2",
  ttsModel: "speech-2.8-turbo",
  ttsVolume: 2.0,
  compactionRetainedTurns: 2,
});

type ModelCapacity = Pick<ModelRegistrationFormData, "modelContextWindow" | "modelAutoCompactTokenLimit">;

/**
 * Validates entered model capacities per field, shared by the settings page,
 * first-run setup and the persistence boundary. An empty window stays
 * saveable as an incomplete registration, so the threshold is then only
 * checked on its own; with a valid window it must stay below it.
 */
export function modelCapacityErrors({ modelContextWindow: contextWindow, modelAutoCompactTokenLimit: limit }: ModelCapacity) {
  const errors: Partial<Record<keyof ModelCapacity, string>> = {};
  const windowValid = contextWindow != null && Number.isSafeInteger(contextWindow) && contextWindow > 0;
  if (contextWindow != null && !windowValid) errors.modelContextWindow = "上下文窗口必须是正整数";
  if (limit != null) {
    if (!Number.isSafeInteger(limit) || limit <= 0) errors.modelAutoCompactTokenLimit = "自动压缩阈值必须是正整数";
    else if (windowValid && limit >= contextWindow) errors.modelAutoCompactTokenLimit = "自动压缩阈值必须小于上下文窗口";
  }
  return errors;
}

/** First capacity error reason, or null when every entered capacity is valid. */
export function modelCapacityError(registration: ModelCapacity) {
  const errors = modelCapacityErrors(registration);
  return errors.modelContextWindow ?? errors.modelAutoCompactTokenLimit ?? null;
}

/** Validates completed-turn retention at both draft and persistence boundaries. */
export function compactionRetainedTurnsError(value: unknown) {
  const retainedTurns = value === undefined ? desktopSettingsDefaults.compactionRetainedTurns : value;
  return typeof retainedTurns === "number" && Number.isSafeInteger(retainedTurns) && retainedTurns >= 0
    ? null
    : "压缩后保留原文轮数必须是非负整数";
}
