/** Defaults shared by the desktop settings reader and writer. */
export const desktopSettingsDefaults = Object.freeze({
  asrProvider: "tencent",
  asrBaseUrl: "https://asr.tencentcloudapi.com/",
  ttsProvider: "minimax",
  ttsBaseUrl: "https://api.minimaxi.com/v1/t2a_v2",
  ttsModel: "speech-2.8-turbo",
  ttsVolume: 2.0,
  novelaiBaseUrl: "https://image.novelai.net",
  novelaiDefaultModel: "nai-diffusion-4-5-curated",
  novelaiNsfwModel: "nai-diffusion-4-5-full",
});
