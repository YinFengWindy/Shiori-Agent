import type React from "react";
import {
  getChatMessageCopyText,
  getChatMessageReplyContent,
  type MessageContextMenuState,
} from "./chatMessageActions";
import { CopyIcon, QuoteIcon } from "../shared/icons";

type ChatMessageContextMenuProps = {
  menu: MessageContextMenuState;
  menuRef: React.RefObject<HTMLDivElement | null>;
  sending: boolean;
  onCopy: () => void;
  onQuote: () => void;
};

/** Renders the copy and quote actions for one chat message. */
export function ChatMessageContextMenu({
  menu,
  menuRef,
  sending,
  onCopy,
  onQuote,
}: ChatMessageContextMenuProps) {
  return (
    <div
      ref={menuRef}
      data-testid="message-context-menu"
      className="fixed z-50 min-w-[132px] overflow-hidden rounded-md border border-[#E4E7EC] bg-white py-1 text-sm text-[#1F2937] shadow-[0_16px_40px_rgba(15,23,42,0.16)]"
      style={{ left: menu.x, top: menu.y }}
      role="menu"
      onClick={(event) => event.stopPropagation()}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <button
        data-testid="message-context-menu-copy"
        className="flex h-8 w-full items-center gap-2 px-3 text-left transition hover:bg-[#F5F7FA] focus:bg-[#F5F7FA] focus:outline-none disabled:cursor-default disabled:opacity-45"
        type="button"
        role="menuitem"
        onClick={onCopy}
        disabled={!getChatMessageCopyText(menu.message)}
      >
        <CopyIcon className="h-[14px] w-[14px] fill-current" />
        <span>复制</span>
      </button>
      <button
        data-testid="message-context-menu-quote"
        className="flex h-8 w-full items-center gap-2 px-3 text-left transition hover:bg-[#F5F7FA] focus:bg-[#F5F7FA] focus:outline-none disabled:cursor-default disabled:opacity-45"
        type="button"
        role="menuitem"
        onClick={onQuote}
        disabled={!getChatMessageReplyContent(menu.message) || sending}
      >
        <QuoteIcon className="h-[14px] w-[14px] fill-current" />
        <span>引用</span>
      </button>
    </div>
  );
}
