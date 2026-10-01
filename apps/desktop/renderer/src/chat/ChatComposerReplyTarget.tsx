import { cx } from "@shiori/sdk";
import { DeleteIcon } from "../shared/icons";
import {
  focusResetClass, replyQuoteButtonClass, replyQuoteFrameClass, replyQuoteSenderClass, replyQuoteTextClass,
} from "../shared/styles";
import type { ChatReplyTarget } from "../shared/types";

type ChatComposerReplyTargetProps = {
  replyTarget: ChatReplyTarget;
  disabled: boolean;
  onClear: () => void;
  onJumpToMessage: (messageKey: string) => void;
};

function ReplyQuote({ replyTarget }: { replyTarget: ChatReplyTarget }) {
  return (
    <div className={replyQuoteFrameClass}>
      <div className={replyQuoteSenderClass}>{replyTarget.sender || "历史消息"}</div>
      <div className={cx(replyQuoteTextClass, "line-clamp-2 text-ink-secondary")}>{replyTarget.preview}</div>
    </div>
  );
}

/** The quoted message pinned above the composer text, with jump-to-source and remove. */
export function ChatComposerReplyTarget({ replyTarget, disabled, onClear, onJumpToMessage }: ChatComposerReplyTargetProps) {
  return (
    <div className="flex min-w-0 items-start gap-2 rounded-md border border-line-soft bg-surface-soft px-2.5 py-2 text-left">
      {replyTarget.messageId ? (
        <button
          className={cx(replyQuoteButtonClass, focusResetClass, "min-w-0 flex-1")}
          type="button"
          aria-label="跳转到引用来源消息"
          onClick={() => onJumpToMessage(replyTarget.messageId)}
        >
          <ReplyQuote replyTarget={replyTarget} />
        </button>
      ) : (
        <div className="min-w-0 flex-1"><ReplyQuote replyTarget={replyTarget} /></div>
      )}
      <button
        className="grid h-6 w-6 flex-none place-items-center rounded-md border-0 bg-transparent p-0 text-ink-faint transition hover:bg-accent-softer hover:text-ink focus:outline-none disabled:cursor-default disabled:opacity-40"
        type="button"
        aria-label="取消引用"
        onClick={onClear}
        disabled={disabled}
      >
        <DeleteIcon className="h-[10px] w-[10px] fill-current" />
      </button>
    </div>
  );
}
