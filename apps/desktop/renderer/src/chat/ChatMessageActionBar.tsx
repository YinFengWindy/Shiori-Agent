import { ArrowClockwise } from "@phosphor-icons/react";
import type React from "react";
import { CopyIcon, QuoteIcon } from "../shared/icons";
import { compactPressableClass, cx } from "../shared/styles";
import { Tooltip } from "../shared/ui/Tooltip";
import type { ChatMessageActionAvailability } from "./chatMessageActions";

type ChatMessageActionBarProps = {
  availability: ChatMessageActionAvailability;
  /** Which side of the bubble the bar sits beside (outside it, bottom-aligned): toward the conversation's centre. */
  side: "left" | "right";
  onCopy: () => void;
  onQuote: () => void;
  onRetry: () => void;
};

const actionButtonClass = cx(
  compactPressableClass,
  "grid h-7 w-7 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink",
);

function ActionButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <Tooltip label={label} side="top">
      <button className={actionButtonClass} type="button" aria-label={label} onClick={onClick}>
        {children}
      </button>
    </Tooltip>
  );
}

/**
 * The small glass toolbar that appears over a message on hover or when
 * keyboard focus enters it (the buttons stay in the tab order while hidden,
 * so focusing one reveals the bar). Mirrors the right-click menu.
 */
export function ChatMessageActionBar({ availability, side, onCopy, onQuote, onRetry }: ChatMessageActionBarProps) {
  if (!availability.copy && !availability.quote && !availability.retry) return null;
  return (
    <div
      className={cx(
        "chat-message-actions surface-glass-strong pointer-events-none absolute bottom-0 z-[2] flex items-center gap-0.5 rounded-md p-0.5 opacity-0 transition-opacity duration-quick",
        "group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100",
        side === "right" ? "left-full ml-1.5" : "right-full mr-1.5",
      )}
      role="toolbar"
      aria-label="消息操作"
      data-testid="chat-message-actions"
    >
      {availability.retry ? (
        <ActionButton label="重试" onClick={onRetry}>
          <ArrowClockwise className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        </ActionButton>
      ) : null}
      {availability.copy ? (
        <ActionButton label="复制" onClick={onCopy}>
          <CopyIcon className="h-[13px] w-[13px] fill-current" />
        </ActionButton>
      ) : null}
      {availability.quote ? (
        <ActionButton label="引用" onClick={onQuote}>
          <QuoteIcon className="h-[13px] w-[13px] fill-current" />
        </ActionButton>
      ) : null}
    </div>
  );
}
