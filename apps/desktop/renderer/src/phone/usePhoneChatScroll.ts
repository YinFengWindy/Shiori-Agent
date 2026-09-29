import { useEffect, useLayoutEffect, useRef } from "react";
import type { PhoneMessage } from "./phoneClient";

// Within this many px of an edge counts as being there.
const bottomSlackPx = 24;
const olderPageTriggerPx = 48;

/**
 * Scrolling of the phone's chat page: it opens at the newest message and
 * stays pinned there while new messages or late-loading images grow the
 * list, unless the reader scrolled up; reaching the top loads the older
 * page, keeping the messages in view where they were.
 */
export function usePhoneChatScroll({ messages, hasMore, loadOlder }: {
  messages: readonly PhoneMessage[] | null;
  hasMore: boolean;
  loadOlder: () => Promise<void>;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  // What the last layout left: the first message shown, the list's height, whether it sat at the bottom.
  const anchorRef = useRef({ firstId: null as string | null, scrollHeight: 0, atBottom: true });

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const anchor = anchorRef.current;
    if (!messages) {
      // Nothing loaded (first open, or a retry reloading): the next page opens at its newest message.
      anchor.firstId = null;
      anchor.atBottom = true;
      return;
    }
    if (!viewport) return;
    const firstId = messages[0]?.id ?? null;
    if (anchor.atBottom) {
      viewport.scrollTop = viewport.scrollHeight;
    } else if (anchor.firstId !== null && firstId !== anchor.firstId) {
      // An older page went in above: shift by its height so the view does not jump.
      viewport.scrollTop += viewport.scrollHeight - anchor.scrollHeight;
    }
    anchor.firstId = firstId;
    anchor.scrollHeight = viewport.scrollHeight;
  }, [messages]);

  // A page too short to scroll can never reach the top by scrolling: fetch older right away.
  useEffect(() => {
    const viewport = viewportRef.current;
    if (viewport && messages && hasMore && viewport.scrollHeight <= viewport.clientHeight) void loadOlder();
  }, [messages, hasMore, loadOlder]);

  useEffect(() => {
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!viewport || !content) return;
    const observer = new ResizeObserver(() => {
      if (anchorRef.current.atBottom) viewport.scrollTop = viewport.scrollHeight;
      anchorRef.current.scrollHeight = viewport.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    anchorRef.current.atBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < bottomSlackPx;
    if (viewport.scrollTop < olderPageTriggerPx) void loadOlder();
  };

  return { viewportRef, contentRef, onScroll };
}
