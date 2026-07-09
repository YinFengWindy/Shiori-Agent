import React, { useEffect, useRef } from "react";
import { commonChatEmojis } from "./chatEmojiState";
import { SmileyIcon } from "../shared/icons";

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
        className="grid h-[30px] w-[30px] place-items-center rounded-md border-0 bg-transparent p-0 text-[#4B5563] transition hover:bg-black/5 hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40"
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
        <div
          className="absolute bottom-[calc(100%+10px)] right-0 z-[4] w-[232px] rounded-[18px] border border-[#E4E7EC] bg-[rgba(255,255,255,0.98)] p-3 shadow-[0_18px_42px_rgba(15,23,42,0.14)] backdrop-blur-[10px]"
          role="dialog"
          aria-label="常用表情面板"
        >
          <div className="mb-2 text-[11px] font-medium tracking-[0.08em] text-[#8B95A7]">常用表情</div>
          <div className="grid grid-cols-6 gap-1.5">
            {commonChatEmojis.map((emoji) => (
              <button
                key={emoji}
                className="grid h-8 w-8 place-items-center rounded-md border border-transparent bg-transparent p-0 text-[19px] leading-none transition hover:border-[#D8DEE8] hover:bg-[#F8FAFC] focus:outline-none"
                type="button"
                aria-label={`插入表情 ${emoji}`}
                onClick={() => onSelectEmoji(emoji)}
              >
                {emoji}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
