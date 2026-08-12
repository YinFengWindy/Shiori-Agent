import React from "react";
import { CaretDown, Sparkle } from "@phosphor-icons/react";
import { cx } from "../shared/styles";
import { formatThinkingDuration } from "./chatTurnMetrics";

type ChatThinkingBlockProps = {
  content: string;
  streaming: boolean;
  thinkingDurationMs?: number;
};

/** Renders the expandable Thinking trace used by streaming assistant replies. */
export const ChatThinkingBlock = React.memo(function ChatThinkingBlock({
  content,
  streaming,
  thinkingDurationMs,
}: ChatThinkingBlockProps) {
  const [expanded, setExpanded] = React.useState(true);
  if (!content) return null;

  return (
    <div className="chat-thinking-block mb-2 max-w-full">
      <button
        type="button"
        aria-expanded={expanded}
        className="-mx-1.5 flex items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] font-medium text-[#626A78] transition-colors duration-150 hover:bg-black/[0.04]"
        onClick={() => setExpanded((current) => !current)}
      >
        <Sparkle size={15} weight="fill" className="text-[#8B95A7]" aria-hidden="true" />
        <span className={cx("chat-thinking-label", streaming && "chat-thinking-label-streaming")}>
          {streaming || thinkingDurationMs === undefined ? "Thinking" : formatThinkingDuration(thinkingDurationMs)}
        </span>
        <CaretDown
          size={14}
          className={cx("text-[#8B95A7] transition-transform duration-200", expanded && "rotate-180")}
          aria-hidden="true"
        />
      </button>
      <div className={cx("chat-thinking-content", expanded && "chat-thinking-content-expanded")}>
        <div className="relative ml-[5px] border-l border-[#E1E5EA] pl-4 pt-1 text-[12px] leading-5 text-[#7A8290]">
          <div className="whitespace-pre-wrap break-words">{content}</div>
          {streaming ? <span className="chat-stream-cursor ml-0.5" aria-hidden="true" /> : null}
        </div>
      </div>
    </div>
  );
});
