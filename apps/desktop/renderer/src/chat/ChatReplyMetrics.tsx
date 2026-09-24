import React from "react";
import { StopCircle } from "@phosphor-icons/react";
import type { ChatTurnMetrics as ChatTurnMetricsValue } from "../shared/types";
import { formatThinkingDuration, formatTokenUsage } from "./chatTurnMetrics";

type ChatReplyMetricsProps = {
  metrics: ChatTurnMetricsValue;
  hasThinking: boolean;
  /** The user stopped this reply mid-stream; its text is only what arrived before the stop. */
  interrupted?: boolean;
};

/** Renders the compact footer below one finished reply: stop marker, latency and provider usage. */
export const ChatReplyMetrics = React.memo(function ChatReplyMetrics({
  metrics,
  hasThinking,
  interrupted = false,
}: ChatReplyMetricsProps) {
  const showDuration = !hasThinking && metrics.thinking_duration_ms !== undefined;
  if (!interrupted && !showDuration && metrics.total_tokens === undefined) return null;

  return (
    <div className="mt-2 flex items-center gap-2 text-[11px] tabular-nums text-ink-faint">
      {interrupted ? (
        <span className="inline-flex items-center gap-1 text-ink-muted" data-testid="chat-reply-interrupted">
          <StopCircle className="h-3.5 w-3.5" aria-hidden="true" />
          已中断
        </span>
      ) : null}
      {showDuration ? <span>{formatThinkingDuration(metrics.thinking_duration_ms!)}</span> : null}
      {metrics.total_tokens !== undefined ? <span>{formatTokenUsage(metrics.total_tokens)}</span> : null}
    </div>
  );
});
