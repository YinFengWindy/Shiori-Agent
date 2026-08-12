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

export function formatThinkingDuration(durationMs: number): string {
  return `Thought for ${(durationMs / 1000).toFixed(1)}s`;
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}
