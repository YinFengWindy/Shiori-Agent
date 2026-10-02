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

/** Validates completed-turn retention at both draft and persistence boundaries. */
export function compactionRetainedTurnsError(value: unknown) {
  const retainedTurns = value === undefined ? desktopSettingsDefaults.compactionRetainedTurns : value;
  return typeof retainedTurns === "number" && Number.isSafeInteger(retainedTurns) && retainedTurns >= 0
    ? null
    : "压缩后保留原文轮数必须是非负整数";
}
