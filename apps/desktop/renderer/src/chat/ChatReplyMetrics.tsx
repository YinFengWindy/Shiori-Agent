import React from "react";
import type { ChatTurnMetrics as ChatTurnMetricsValue } from "../shared/types";
import { formatThinkingDuration } from "./chatTurnMetrics";

type ChatReplyMetricsProps = {
  metrics: ChatTurnMetricsValue;
  hasThinking: boolean;
};

/** Renders compact provider usage and latency metadata below one reply. */
export const ChatReplyMetrics = React.memo(function ChatReplyMetrics({
  metrics,
  hasThinking,
}: ChatReplyMetricsProps) {
  const showDuration = !hasThinking && metrics.thinking_duration_ms !== undefined;
  if (!showDuration && metrics.total_tokens === undefined) return null;

  return (
    <div className="mt-2 flex items-center gap-2 text-[11px] tabular-nums text-[#98A0AD]">
      {showDuration ? <span>{formatThinkingDuration(metrics.thinking_duration_ms!)}</span> : null}
      {metrics.total_tokens !== undefined ? <span>{metrics.total_tokens.toLocaleString()} tokens</span> : null}
    </div>
  );
});
