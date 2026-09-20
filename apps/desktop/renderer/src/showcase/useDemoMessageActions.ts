import { useEffect, useRef, useState } from "react";
import type { ChatReplyTarget, SessionMessage } from "../shared/types";
import { getChatMessageCopyText, getChatMessageReplyContent, type MessageContextMenuState } from "../chat/chatMessageActions";
import { summarizeChatReplyContent } from "../chat/chatComposerState";

/** Bind the product's copy/quote menu to browser clipboard and in-page navigation. */
export function useDemoMessageActions() {
  const [menu, setMenu] = useState<MessageContextMenuState | null>(null);
  const [replyTarget, setReplyTarget] = useState<ChatReplyTarget | null>(null);
  const [error, setError] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (event: MouseEvent) => { if (!menuRef.current?.contains(event.target as Node)) setMenu(null); };
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") setMenu(null); };
    document.addEventListener("click", close);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("click", close); document.removeEventListener("keydown", key); };
  }, [menu]);
  return {
    menu, menuRef, replyTarget, error,
    clearReply: () => setReplyTarget(null),
    openMenu(event: React.MouseEvent<HTMLElement>, message: SessionMessage, messageKey: string, sender: string) {
      event.preventDefault();
      setMenu({ x: Math.min(event.clientX, window.innerWidth - 150), y: Math.min(event.clientY, window.innerHeight - 100), message, messageKey, sender });
    },
    async copy() {
      if (!menu) return;
      try { await navigator.clipboard.writeText(getChatMessageCopyText(menu.message)); }
      catch { setError("浏览器未允许复制，请直接选中文字复制。"); }
      setMenu(null);
    },
    quote() {
      if (!menu) return;
      const content = getChatMessageReplyContent(menu.message);
      setReplyTarget({ messageId: menu.messageKey, content, sender: menu.sender, preview: summarizeChatReplyContent(content) });
      setMenu(null);
    },
    jump(messageKey: string) {
      document.querySelector(`[data-message-key="${CSS.escape(messageKey)}"]`)?.scrollIntoView({ block: "center", behavior: "instant" });
    },
  };
}
