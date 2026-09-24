import React from "react";
import { ArrowClockwise, CaretDown, WarningCircle } from "@phosphor-icons/react";
import { compactPressableClass, cx } from "../shared/styles";
import { splitChatErrorContent } from "./chatFailedTurn";

type ChatErrorRowProps = {
  content: string;
  /** Only the conversation's latest failed turn can be retried. */
  canRetry: boolean;
  onRetry: () => void;
};

const inlineButtonClass = cx(
  compactPressableClass,
  "inline-flex h-6 flex-none items-center gap-1 rounded-md px-1.5 text-caption font-medium hover:bg-white/70",
);

/**
 * A failed turn, drawn as a system row in the middle of the timeline instead
 * of a bubble from the role: it is not something the role said. Long raw
 * errors collapse behind 「详情」; the latest one offers 重试.
 */
export function ChatErrorRow({ content, canRetry, onRetry }: ChatErrorRowProps) {
  const { summary, detail } = splitChatErrorContent(content);
  const [expanded, setExpanded] = React.useState(false);
  return (
    <div className="chat-error-row mx-auto grid w-fit max-w-[82%] gap-1 rounded-lg bg-danger-soft px-3 py-2 text-body-sm text-danger-text shadow-soft" role="alert">
      <div className="flex min-w-0 items-center gap-2">
        <WarningCircle className="h-4 w-4 flex-none" weight="fill" aria-hidden="true" />
        <span className="min-w-0 break-words">{summary}</span>
        {detail ? (
          <button className={inlineButtonClass} type="button" aria-expanded={expanded} onClick={() => setExpanded((current) => !current)}>
            详情
            <CaretDown className={cx("h-3 w-3 transition-transform duration-quick", expanded && "rotate-180")} aria-hidden="true" />
          </button>
        ) : null}
        {canRetry ? (
          <button className={inlineButtonClass} type="button" onClick={onRetry} data-testid="chat-error-retry">
            <ArrowClockwise className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            重试
          </button>
        ) : null}
      </div>
      {detail && expanded ? (
        <pre className="scrollbar-soft max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-white/60 p-2 font-mono text-caption text-ink-secondary">{detail}</pre>
      ) : null}
    </div>
  );
}
