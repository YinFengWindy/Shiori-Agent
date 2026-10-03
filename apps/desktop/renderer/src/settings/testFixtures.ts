import type { SettingsFormData } from "../../../src/bridge/shared.js";

/** Builds independent complete settings drafts for transaction tests. */
export function createSettingsDraft(): SettingsFormData {
  return {
    proactiveStrategies: {},
    models: { registrations: [] },
    memory: { enabled: false, engine: "default", embeddingModel: "", embeddingApiKey: "", embeddingBaseUrl: "", outputDimensionality: "" },
    voice: { enabled: false, hotkey: "Ctrl+Space", microphoneDeviceId: "", asrProvider: "tencent", asrBaseUrl: "", asrSecretId: "", asrSecretKey: "", ttsProvider: "minimax", ttsBaseUrl: "", ttsModel: "", ttsApiKey: "", ttsVolume: 2 },
    advanced: { maxTokens: 4000, maxIterations: 10, devMode: false, streamingEnabled: false, memoryWindow: 20, compactionRetainedTurns: 2, summaryTokenLimit: 2000, searchEnabled: true, spawnEnabled: true, memoryOptimizerEnabled: false, memoryOptimizerIntervalSeconds: 3600, contextTriggerRatio: 0.75, contextTargetRatio: 0.4, contextSafetyMarginTokens: 4096 },
  };
}
