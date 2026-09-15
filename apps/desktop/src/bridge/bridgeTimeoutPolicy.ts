/** Time limits shared by the Electron bridge command boundary. */
export const bridgeTimeoutPolicy = Object.freeze({
  health: 5_000,
  startup: 60_000,
  defaultRequest: 30_000,
  voiceRequest: 30_000,
  gracefulStop: 5_000,
  forcedStop: 2_000,
});

/** Returns a deadline, or null for a transaction that must await its committed outcome. */
export function bridgeRequestTimeoutMs(method: string, requestedTimeoutMs?: number): number | null {
  if (method === "runtime.apply") return null;
  if (requestedTimeoutMs !== undefined) {
    if (!Number.isInteger(requestedTimeoutMs) || requestedTimeoutMs <= 0 || requestedTimeoutMs > 2_147_483_647) {
      throw new Error("请求超时必须是有效的正整数毫秒数");
    }
    return requestedTimeoutMs;
  }
  if (method === "health") return bridgeTimeoutPolicy.health;
  if (method.startsWith("voice.")) return bridgeTimeoutPolicy.voiceRequest;
  return bridgeTimeoutPolicy.defaultRequest;
}
