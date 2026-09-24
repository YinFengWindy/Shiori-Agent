import { ArrowDown } from "@phosphor-icons/react";
import { compactPressableClass, cx } from "../shared/styles";

/**
 * Jumps back to the newest message. It sits at the right edge of the message
 * track just above the composer (`--chat-composer-height`), clear of the
 * left-aligned replies and their code blocks, and pops in with a small scale.
 */
export function ChatScrollToBottomButton({ onClick }: { onClick: () => void }) {
  return (
    <div
      className="pointer-events-none absolute inset-x-0 z-[2] mx-auto flex w-full max-w-[700px] justify-end px-5 md:px-6"
      style={{ bottom: "calc(var(--chat-composer-height, 96px) + 52px)" }}
    >
      <button
        className={cx(
          compactPressableClass,
          "chat-scroll-bottom-enter surface-glass-strong pointer-events-auto grid h-9 w-9 origin-bottom place-items-center rounded-full text-ink-secondary hover:bg-white hover:text-ink",
        )}
        type="button"
        aria-label="滑到最下方"
        data-testid="chat-scroll-to-bottom"
        onClick={onClick}
      >
        <ArrowDown className="h-4 w-4" weight="bold" aria-hidden="true" />
      </button>
    </div>
  );
}
