import { ArrowDown } from "@phosphor-icons/react";
import { chatContentTrackMaxWidthPx } from "./ChatMessageList";
import { compactPressableClass, cx } from "../shared/styles";

/**
 * Jumps back to the newest message. It floats just above the composer
 * (`--chat-composer-height`) in the right gutter beside the message track —
 * clear of replies, their code blocks and the user's bubbles whenever the
 * pane is wider than the track — and pops in with a small scale.
 */
export function ChatScrollToBottomButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      className={cx(
        compactPressableClass,
        "chat-scroll-bottom-enter surface-glass-strong absolute z-[2] grid h-9 w-9 origin-bottom place-items-center rounded-full text-ink-secondary hover:bg-white hover:text-ink",
      )}
      style={{
        bottom: "calc(var(--chat-composer-height, 96px) + 52px)",
        // Half the gutter minus the button and a little air; never closer than 12px to the edge.
        right: `max(12px, calc((100% - ${chatContentTrackMaxWidthPx}px) / 2 - 28px))`,
      }}
      type="button"
      aria-label="滑到最下方"
      data-testid="chat-scroll-to-bottom"
      onClick={onClick}
    >
      <ArrowDown className="h-4 w-4" weight="bold" aria-hidden="true" />
    </button>
  );
}
