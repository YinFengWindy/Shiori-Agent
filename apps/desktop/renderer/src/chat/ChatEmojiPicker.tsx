import React, { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { commonChatEmojis } from "./chatEmojiState";
import { useChatComposerPopover } from "./useChatComposerPopover";
import { SmileyIcon } from "../shared/icons";
import { MenuPanel } from "../shared/ui/Menu";

type ChatEmojiPickerProps = {
  disabled: boolean;
  open: boolean;
  onClose: () => void;
  onSelectEmoji: (emoji: string) => void;
  onToggle: () => void;
};

/** Width of the panel (`w-[232px]`); the position clamp needs it before the panel renders. */
const panelWidth = 232;

/** Distance between the panel and the smiley button. */
const panelGap = 10;

/**
 * Renders the lightweight desktop emoji picker for the chat composer. The
 * panel is portalled to the body and placed above the smiley button in window
 * coordinates, so the composer card's clipping never cuts it and a short
 * window makes it scroll instead of running off the top.
 */
export function ChatEmojiPicker({
  disabled,
  open,
  onClose,
  onSelectEmoji,
  onToggle,
}: ChatEmojiPickerProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const position = useChatComposerPopover({
    open,
    onClose,
    triggerRef: buttonRef,
    popoverRef: panelRef,
    width: panelWidth,
    align: "end",
    gap: panelGap,
  });
  const placed = position !== null;

  useEffect(() => {
    if (disabled && open) {
      onClose();
    }
  }, [disabled, onClose, open]);

  // The panel lives at the end of <body>, away from the button in tab order,
  // so keyboard users are taken into it on open.
  useEffect(() => {
    if (!placed) return;
    panelRef.current?.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
  }, [placed]);

  // Tabbing past either end of the grid would otherwise drop focus at the end
  // of the document: close and hand focus back to the button instead.
  function handlePanelKeyDown(event: React.KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "Tab") return;
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("button"));
    const edge = event.shiftKey ? buttons[0] : buttons.at(-1);
    if (document.activeElement !== edge) return;
    event.preventDefault();
    onClose();
    buttonRef.current?.focus();
  }

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        className="grid h-[30px] w-[30px] place-items-center rounded-md border-0 bg-transparent p-0 text-ink-secondary transition hover:bg-black/5 hover:text-ink disabled:cursor-default disabled:opacity-40"
        type="button"
        aria-label={open ? "收起常用表情面板" : "打开常用表情面板"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={onToggle}
        disabled={disabled}
      >
        <SmileyIcon className="h-[16px] w-[16px] stroke-current" />
      </button>
      {open && position ? createPortal(
        <div className="motion-popover-enter fixed z-50 origin-bottom-right" style={{ left: position.left, bottom: position.bottom }}>
          <MenuPanel
            ref={panelRef}
            className="w-[232px] overflow-y-auto overscroll-contain p-3"
            style={{ maxHeight: position.maxHeight }}
            role="dialog"
            aria-label="常用表情面板"
            onKeyDown={handlePanelKeyDown}
          >
            <div className="mb-2 text-[11px] font-medium tracking-[0.08em] text-ink-faint">常用表情</div>
            <div className="grid grid-cols-6 gap-1.5">
              {commonChatEmojis.map((emoji) => (
                <button
                  key={emoji}
                  className="grid h-8 w-8 place-items-center rounded-md border border-transparent bg-transparent p-0 text-[19px] leading-none transition hover:border-line-soft hover:bg-surface-soft"
                  type="button"
                  aria-label={`插入表情 ${emoji}`}
                  onClick={() => onSelectEmoji(emoji)}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </MenuPanel>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
