import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React, { act, useCallback, useRef } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useChatMessageVirtualization } from "./useChatMessageVirtualization";

describe("useChatMessageVirtualization", () => {
  it("restores virtual coordinates from previously measured offscreen rows when returning to a session", async () => {
    const messages = Array.from({ length: 601 }, (_, index) => ({ id: `message-${index}`, role: "assistant", content: "reply" }));
    let virtualization!: ReturnType<typeof useChatMessageVirtualization>;
    function Harness({ sessionKey }: { sessionKey: string }) {
      const containerRef = useRef<HTMLDivElement | null>(null);
      const autoRef = useRef(false);
      const attach = useCallback((element: HTMLDivElement | null) => {
        containerRef.current = element;
        if (element) {
          Object.defineProperty(element, "clientHeight", { value: 600 });
          element.scrollTop = 30000;
        }
      }, []);
      virtualization = useChatMessageVirtualization({
        sessionKey, messages, messageStartIndex: 0, highlightedMessageKey: "",
        conversationListRef: containerRef, isAutoScrollingRef: autoRef,
      });
      return <div ref={attach} />;
    }
    const view = await mountTestComponent(<Harness sessionKey="first" />);
    try {
      const measureAndUnmount = async (index: number, height: number) => {
        const element = document.createElement("article");
        element.getBoundingClientRect = () => ({
          x: 0, y: 1, width: 100, height, top: 1, right: 100, bottom: height + 1, left: 0, toJSON: () => ({}),
        });
        await act(async () => {
          virtualization.observeMessageElement(messages[index]!, index, element);
          virtualization.observeMessageElement(messages[index]!, index, null);
        });
      };
      await measureAndUnmount(0, 400);
      await measureAndUnmount(1, 300);
      const original = virtualization.virtualMessageWindow;
      await view.render(<Harness sessionKey="second" />);
      await measureAndUnmount(0, 900);
      assert.notEqual(virtualization.virtualMessageWindow.totalHeight, original.totalHeight);
      await view.render(<Harness sessionKey="first" />);
      assert.equal(virtualization.virtualMessageWindow.totalHeight, original.totalHeight);
      assert.equal(virtualization.virtualMessageWindow.firstVisibleIndex, original.firstVisibleIndex);
      assert.equal(virtualization.virtualMessageWindow.topSpacerHeight, original.topSpacerHeight);
    } finally { await view.cleanup(); }
  });

  it("keeps mounted rows observed across session changes and late height changes", async () => {
    const observers: TestResizeObserver[] = [];
    class TestResizeObserver {
      elements = new Set<Element>();
      constructor(readonly callback: ResizeObserverCallback) { observers.push(this); }
      observe(element: Element) { this.elements.add(element); }
      unobserve(element: Element) { this.elements.delete(element); }
      disconnect() { this.elements.clear(); }
    }
    const messages = [{ id: "message", role: "assistant", content: "reply" }];
    let changes = 0;
    const onContentSizeChange = () => { changes += 1; };
    function Harness({ sessionKey }: { sessionKey: string }) {
      const containerRef = useRef<HTMLDivElement>(null);
      const scrollingRef = useRef(false);
      const { observeMessageElement } = useChatMessageVirtualization({
        sessionKey, messages, messageStartIndex: 0, highlightedMessageKey: "",
        conversationListRef: containerRef, isAutoScrollingRef: scrollingRef, onContentSizeChange,
      });
      const rowRef = useCallback((element: HTMLElement | null) => {
        observeMessageElement(messages[0]!, 0, element);
      }, [observeMessageElement]);
      return <div ref={containerRef}><article ref={rowRef}>reply</article></div>;
    }
    const frames = new Map<number, FrameRequestCallback>();
    let frameId = 0;
    const view = await mountTestComponent(<Harness sessionKey="first" />, {
      windowGlobals: {
        ResizeObserver: TestResizeObserver,
        requestAnimationFrame: (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; },
        cancelAnimationFrame: (id: number) => { frames.delete(id); },
      },
    });
    try {
      for (const sessionKey of ["first", "second"]) {
        if (sessionKey === "second") await view.render(<Harness sessionKey={sessionKey} />);
        const article = view.container.querySelector("article")!;
        const observer = observers.find((candidate) => candidate.elements.has(article));
        assert.ok(observer, `row remains observed in ${sessionKey} session`);
        const before = changes;
        await act(async () => {
          observer.callback([{
            target: article,
            contentRect: { x: 0, y: 0, width: 100, height: 320, top: 0, right: 100, bottom: 320, left: 0, toJSON: () => ({}) },
            borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [],
          }], observer);
          const pending = [...frames.values()];
          frames.clear();
          pending.forEach((callback) => callback(16));
        });
        assert.ok(changes > before, "late row growth notifies the bottom follower");
      }
    } finally { await view.cleanup(); }
  });
});
