/** Time limits shared by the Electron bridge command boundary. */
export const bridgeTimeoutPolicy = Object.freeze({
  health: 5_000,
  defaultRequest: 30_000,
  voiceRequest: 60_000,
  imageGeneration: 5 * 60_000,
  observation: 2 * 60_000,
  gracefulStop: 5_000,
  forcedStop: 2_000,
});

const imageGenerationMethods = new Set([
  "novelai.generate",
  "novelai.regenerateMessageMedia",
  "roles.differences.generate",
]);

/** Returns the deadline for one bridge request method. */
export function bridgeRequestTimeoutMs(method: string): number {
  if (method === "health") return bridgeTimeoutPolicy.health;
  if (imageGenerationMethods.has(method)) return bridgeTimeoutPolicy.imageGeneration;
  if (method === "observation.analyze") return bridgeTimeoutPolicy.observation;
  if (method.startsWith("voice.")) return bridgeTimeoutPolicy.voiceRequest;
  return bridgeTimeoutPolicy.defaultRequest;
}
