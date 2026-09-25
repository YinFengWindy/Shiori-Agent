import { ArrowClockwise } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import { compactPressableClass, cx } from "../shared/styles";
import { splitChatErrorContent } from "./chatFailedTurn";

type ChatErrorRowProps = {
  content: string;
  /** The bridge's scrubbed one-line cause, when it reported one. */
  detail?: string;
  /** Only the conversation's latest failed turn can be retried. */
  canRetry: boolean;
  onRetry: () => void;
};

const retryButtonClass = cx(
  compactPressableClass,
  "inline-flex h-6 flex-none items-center gap-1 rounded-md px-1.5 text-caption font-medium text-danger-text hover:bg-white/70",
);

/**
 * A failed turn, drawn as a system row in the middle of the timeline instead
 * of a bubble from the role: it is not something the role said. 吟风 fronts
 * it when the 看板娘 is on; long raw errors collapse behind 「详情」; the
 * latest one offers 重试.
 */
export function ChatErrorRow({ content, detail: reportedDetail = "", canRetry, onRetry }: ChatErrorRowProps) {
  const { summary, detail } = splitChatErrorContent(content, reportedDetail);
  return (
    <InlineError
      className="chat-error-row mx-auto w-fit max-w-[82%] shadow-soft"
      persona="chatTurnFailed"
      message={summary}
      detail={detail || undefined}
      actions={canRetry ? (
        <button className={retryButtonClass} type="button" onClick={onRetry} data-testid="chat-error-retry">
          <ArrowClockwise className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          重试
        </button>
      ) : undefined}
    />
  );
}
