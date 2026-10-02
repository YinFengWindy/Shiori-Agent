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

/**
 * Validates entered model capacities at both draft and persistence boundaries.
 * An empty window stays saveable as an incomplete registration; an auto
 * compaction threshold must be a positive integer below the window.
 */
export function modelCapacityError(registration: Pick<ModelRegistrationFormData, "modelContextWindow" | "modelAutoCompactTokenLimit">) {
  const { modelContextWindow: contextWindow, modelAutoCompactTokenLimit: limit } = registration;
  if (contextWindow != null && (!Number.isSafeInteger(contextWindow) || contextWindow <= 0)) return "上下文窗口必须是正整数";
  if (limit == null) return null;
  if (!Number.isSafeInteger(limit) || limit <= 0) return "自动压缩阈值必须是正整数";
  if (contextWindow == null || limit >= contextWindow) return "自动压缩阈值必须小于上下文窗口";
  return null;
}

/** Validates completed-turn retention at both draft and persistence boundaries. */
export function compactionRetainedTurnsError(value: unknown) {
  const retainedTurns = value === undefined ? desktopSettingsDefaults.compactionRetainedTurns : value;
  return typeof retainedTurns === "number" && Number.isSafeInteger(retainedTurns) && retainedTurns >= 0
    ? null
    : "压缩后保留原文轮数必须是非负整数";
}
