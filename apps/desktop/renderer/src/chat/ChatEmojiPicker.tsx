import React, { useEffect, useRef } from "react";
import { commonChatEmojis } from "./chatEmojiState";
import { SmileyIcon } from "../shared/icons";
import { MenuPanel } from "../shared/ui/Menu";

type ChatEmojiPickerProps = {
  disabled: boolean;
  open: boolean;
  onClose: () => void;
  onSelectEmoji: (emoji: string) => void;
  onToggle: () => void;
};

/** Renders the lightweight desktop emoji picker anchored to the chat composer action row. */
export function ChatEmojiPicker({
  disabled,
  open,
  onClose,
  onSelectEmoji,
  onToggle,
}: ChatEmojiPickerProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function handlePointerDown(event: PointerEvent): void {
      if (rootRef.current?.contains(event.target as Node)) {
        return;
      }
      onClose();
    }

    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("pointerdown", handlePointerDown, true);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown, true);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  useEffect(() => {
    if (disabled && open) {
      onClose();
    }
  }, [disabled, onClose, open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        className="grid h-[30px] w-[30px] place-items-center rounded-md border-0 bg-transparent p-0 text-ink-secondary transition hover:bg-black/5 hover:text-ink focus:outline-none disabled:cursor-default disabled:opacity-40"
        type="button"
        aria-label={open ? "收起常用表情面板" : "打开常用表情面板"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={onToggle}
        disabled={disabled}
      >
        <SmileyIcon className="h-[16px] w-[16px] stroke-current" />
      </button>
      {open ? (
        <MenuPanel
          className="motion-popover-enter absolute bottom-[calc(100%+10px)] right-0 z-[4] w-[232px] origin-bottom-right p-3"
          role="dialog"
          aria-label="常用表情面板"
        >
          <div className="mb-2 text-[11px] font-medium tracking-[0.08em] text-ink-faint">常用表情</div>
          <div className="grid grid-cols-6 gap-1.5">
            {commonChatEmojis.map((emoji) => (
              <button
                key={emoji}
                className="grid h-8 w-8 place-items-center rounded-md border border-transparent bg-transparent p-0 text-[19px] leading-none transition hover:border-line-soft hover:bg-surface-soft focus:outline-none"
                type="button"
                aria-label={`插入表情 ${emoji}`}
                onClick={() => onSelectEmoji(emoji)}
              >
                {emoji}
              </button>
            ))}
          </div>
        </MenuPanel>
      ) : null}
    </div>
  );
}
