import type React from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import type { ChatMessageActionAvailability, MessageContextMenuState } from "./chatMessageActions";
import { CopyIcon, QuoteIcon } from "../shared/icons";
import { MenuItem, MenuPanel } from "../shared/ui/Menu";

type ChatMessageContextMenuProps = {
  menu: MessageContextMenuState;
  menuRef: React.RefObject<HTMLDivElement | null>;
  availability: ChatMessageActionAvailability;
  onCopy: () => void;
  onQuote: () => void;
  onRetry: () => void;
};

/** Renders the right-click actions for one chat message; the same set as its hover bar. */
export function ChatMessageContextMenu({
  menu,
  menuRef,
  availability,
  onCopy,
  onQuote,
  onRetry,
}: ChatMessageContextMenuProps) {
  return (
    <MenuPanel
      ref={menuRef}
      data-testid="message-context-menu"
      className="fixed z-50 min-w-[132px]"
      style={{ left: menu.x, top: menu.y }}
      role="menu"
      onClick={(event) => event.stopPropagation()}
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
