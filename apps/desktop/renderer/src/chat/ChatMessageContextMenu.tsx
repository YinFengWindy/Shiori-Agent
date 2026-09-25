import { useEffect } from "react";
import type React from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import type { ChatMessageActionAvailability, MessageContextMenuState } from "./chatMessageActions";
import { CopyIcon, QuoteIcon } from "../shared/icons";
import { MenuItem, MenuPanel, moveMenuFocus } from "../shared/ui/Menu";

type ChatMessageContextMenuProps = {
  menu: MessageContextMenuState;
  menuRef: React.RefObject<HTMLDivElement | null>;
  availability: ChatMessageActionAvailability;
  onCopy: () => void;
  onQuote: () => void;
  onRetry: () => void;
  /** Closes the menu, handing focus back to the message when it was opened from the keyboard. */
  onClose: () => void;
};

/** The enabled rows, in order: the targets of arrow-key focus. */
const enabledItemSelector = '[role="menuitem"]:not(:disabled)';

/**
 * Renders the per-message actions (重试 / 复制 / 引用), opened by right-click
 * or from the keyboard on a focused message. A keyboard-opened menu focuses
 * its first enabled row; arrow keys, Home and End move between rows, and Tab
 * closes it.
 */
export function ChatMessageContextMenu({
  menu,
  menuRef,
  availability,
  onCopy,
  onQuote,
  onRetry,
  onClose,
}: ChatMessageContextMenuProps) {
  useEffect(() => {
    if (!menu.fromKeyboard) return;
    menuRef.current?.querySelector<HTMLElement>(enabledItemSelector)?.focus({ preventScroll: true });
  }, [menu, menuRef]);

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Tab") {
      event.preventDefault();
      onClose();
      return;
    }
    moveMenuFocus(event, enabledItemSelector);
  }

  return (
    <MenuPanel
      ref={menuRef}
      data-testid="message-context-menu"
      className="fixed z-50 min-w-[132px]"
      style={{ left: menu.x, top: menu.y }}
      role="menu"
      aria-label="消息操作"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={handleKeyDown}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      {availability.retry ? (
        <MenuItem data-testid="message-context-menu-retry" role="menuitem" onClick={onRetry}>
          <ArrowClockwise className="h-[14px] w-[14px]" weight="bold" aria-hidden="true" />
          <span>重试</span>
        </MenuItem>
      ) : null}
      <MenuItem
        data-testid="message-context-menu-copy"
        role="menuitem"
        onClick={onCopy}
        disabled={!availability.copy}
      >
        <CopyIcon className="h-[14px] w-[14px] fill-current" />
        <span>复制</span>
      </MenuItem>
      <MenuItem
        data-testid="message-context-menu-quote"
        role="menuitem"
        onClick={onQuote}
        disabled={!availability.quote}
      >
        <QuoteIcon className="h-[14px] w-[14px] fill-current" />
        <span>引用</span>
      </MenuItem>
    </MenuPanel>
  );
}
