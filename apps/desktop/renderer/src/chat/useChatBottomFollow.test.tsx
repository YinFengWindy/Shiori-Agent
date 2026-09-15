import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React, { act, useCallback, useRef } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useChatBottomFollow } from "./useChatBottomFollow";

describe("useChatBottomFollow", () => {
  it("preserves following across delayed program scrolls and resumes only after downward movement or a bottom request", async () => {
    let follow!: ReturnType<typeof useChatBottomFollow>;
    let height = 1200;
    let viewportHeight = 600;
    let resize!: () => void;
    const loadedAt: number[] = [];
    class TestResizeObserver {
      constructor(callback: () => void) { resize = callback; }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    function Harness({ highlighted = "" }: { highlighted?: string }) {
      const containerRef = useRef<HTMLDivElement | null>(null);
      const autoRef = useRef(false);
      const attach = useCallback((element: HTMLDivElement | null) => {
        containerRef.current = element;
        if (element) {
          Object.defineProperties(element, {
            scrollHeight: { get: () => height }, clientHeight: { get: () => viewportHeight },
          });
          element.scrollTop = 600;
        }
      }, []);
      const scrollToBottom = useCallback(() => {
        containerRef.current!.scrollTop = height - viewportHeight;
      }, []);
      const cancelScroll = useCallback(() => { autoRef.current = false; }, []);
      follow = useChatBottomFollow({
        conversationListRef: containerRef, isAutoScrollingRef: autoRef, sessionKey: "session",
        highlightedMessageKey: highlighted, scrollToBottom, cancelScroll,
        maybeLoadOlderMessages: (top) => { loadedAt.push(top); },
      });
      return <div ref={attach} />;
    }
    const view = await mountTestComponent(<Harness />, { windowGlobals: { ResizeObserver: TestResizeObserver } });
    try {
      const container = view.container.firstElementChild as HTMLDivElement;
      const scroll = async (top: number) => act(async () => {
        container.scrollTop = top;
        container.dispatchEvent(new Event("scroll"));
      });
      await act(async () => { height = 1400; follow.handleChatContentSizeChange(); });
      assert.equal(container.scrollTop, 800);
      height = 1500;
      await scroll(800); // A queued event arrives after content grew again.
      assert.equal(follow.stickToBottomRef.current, true);
      await act(async () => follow.handleChatContentSizeChange());
      assert.equal(container.scrollTop, 900);
      await act(async () => container.dispatchEvent(Object.assign(new Event("wheel"), { deltaY: -10 })));
      assert.equal(follow.stickToBottomRef.current, false);
      await scroll(890);
      height = 1600;
      await act(async () => follow.handleChatContentSizeChange());
      assert.equal(container.scrollTop, 890, "reply growth respects even a small upward gesture");
      await scroll(1000);
      assert.equal(follow.stickToBottomRef.current, true, "manually returning down resumes following");
      await act(async () => { viewportHeight = 500; resize(); });
      assert.equal(container.scrollTop, 1100, "a smaller viewport remains bottom anchored");
      await act(async () => container.dispatchEvent(Object.assign(new Event("wheel"), { deltaY: -100 })));
      await scroll(100);
      await act(async () => follow.scrollConversationToBottom("auto"));
      assert.equal(follow.stickToBottomRef.current, true);
      assert.equal(container.scrollTop, 1100);
      await view.render(<Harness highlighted="historical-message" />);
      height = 1700;
      await act(async () => follow.handleChatContentSizeChange());
      assert.equal(container.scrollTop, 1100, "message navigation keeps ownership of its viewport");
      await scroll(400);
      await view.render(<Harness />);
      height = 1800;
      await act(async () => follow.handleChatContentSizeChange());
      assert.equal(container.scrollTop, 400, "clearing the navigation highlight does not re-enable following");
      assert.ok(loadedAt.includes(100), "user scrolling still reaches the history pagination owner");
    } finally { await view.cleanup(); }
  });
});
