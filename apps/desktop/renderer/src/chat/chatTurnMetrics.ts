import type { ChatTurnMetrics } from "../shared/types";

/** Reads the public turn metrics persisted on an assistant message. */
export function parseChatTurnMetrics(value: unknown): ChatTurnMetrics {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const raw = value as Record<string, unknown>;
  return {
    ...(isNonNegativeNumber(raw.total_tokens) ? { total_tokens: raw.total_tokens } : {}),
    ...(isNonNegativeNumber(raw.thinking_duration_ms) ? { thinking_duration_ms: raw.thinking_duration_ms } : {}),
  };
}

/** Formats the persisted thinking time shown on a finished reply, e.g. 「思考 6.2 秒」. */
export function formatThinkingDuration(durationMs: number): string {
  return `思考 ${(durationMs / 1000).toFixed(1)} 秒`;
}

/** Formats the provider token usage shown beneath a finished reply. */
export function formatTokenUsage(totalTokens: number): string {
  return `${totalTokens.toLocaleString()} tokens`;
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}
