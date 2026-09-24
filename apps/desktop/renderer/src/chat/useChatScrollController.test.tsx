import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useCallback, useRef } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useChatScrollController } from "./useChatScrollController";

describe("useChatScrollController", () => {
  it("restores the outgoing session's last position before replacement rows change the shared container", async () => {
    let controller!: ReturnType<typeof useChatScrollController>;
    function Harness({ sessionKey }: { sessionKey: string }) {
      const containerRef = useRef<HTMLDivElement | null>(null);
      controller = useChatScrollController({ conversationListRef: containerRef, sessionKey });
      const attach = useCallback((element: HTMLDivElement | null) => {
        containerRef.current = element;
        if (element) {
          Object.defineProperties(element, {
            clientHeight: { configurable: true, value: 600 },
            scrollHeight: { configurable: true, value: 6000 },
          });
          // Replacement row measurements happen before the owner's layout effect.
          element.scrollTop = sessionKey === "first" ? 0 : 100;
        }
      }, [sessionKey]);
      return <div ref={attach} />;
    }
    const view = await mountTestComponent(<Harness sessionKey="first" />);
    try {
      const container = view.container.firstElementChild as HTMLDivElement;
      await act(async () => {
        container.scrollTop = 600;
        container.dispatchEvent(new Event("scroll"));
      });
      await view.render(<Harness sessionKey="second" />);
      const restored = controller.restoreSessionScroll("first");
      assert.equal(restored?.scrollTop, 600);
      assert.equal(container.scrollTop, 600);
    } finally { await view.cleanup(); }
  });

  it("settles detached navigation exactly once so its owner can release pending state and highlighting", async () => {
    let controller!: ReturnType<typeof useChatScrollController>;
    function Harness() {
      const containerRef = useRef<HTMLDivElement>(null);
      controller = useChatScrollController({ conversationListRef: containerRef, sessionKey: "role:test" });
      return <div ref={containerRef}><div data-target="true" /></div>;
    }
    const view = await mountTestComponent(<Harness />);
    const frames = new Map<number, FrameRequestCallback>();
    let nextFrame = 0;
    window.requestAnimationFrame = (callback) => { frames.set(++nextFrame, callback); return nextFrame; };
    window.cancelAnimationFrame = (frame) => { frames.delete(frame); };
    try {
      const container = view.container.firstElementChild as HTMLDivElement;
      const target = container.firstElementChild as HTMLDivElement;
      Object.defineProperties(container, { clientHeight: { value: 600 }, scrollHeight: { value: 6000 } });
      target.getBoundingClientRect = () => ({ x: 0, y: 4000, top: 4000, bottom: 4100, left: 0, right: 100, width: 100, height: 100, toJSON: () => ({}) });
      let pending = true;
      let highlighted = "target";
      let settleCount = 0;
      await act(async () => controller.scrollToMessage(target, () => {
        pending = false;
        highlighted = "";
        settleCount += 1;
      }));
      assert.equal(controller.isAutoScrollingRef.current, true);
      target.remove();
      const frame = frames.values().next().value!;
      await act(async () => frame(window.performance.now() + 16));
      assert.equal(pending, false);
      assert.equal(highlighted, "");
      assert.equal(controller.isAutoScrollingRef.current, false);
      await act(async () => window.dispatchEvent(new Event("wheel")));
      assert.equal(settleCount, 1);
      assert.equal(frames.size, 0);
    } finally { await view.cleanup(); }
  });

  it("lands smooth scrolls instantly when the OS asks for reduced motion", async () => {
    let controller!: ReturnType<typeof useChatScrollController>;
    function Harness() {
      const containerRef = useRef<HTMLDivElement>(null);
      controller = useChatScrollController({ conversationListRef: containerRef, sessionKey: "role:test" });
      return <div ref={containerRef}><div data-target="true" /></div>;
    }
    const view = await mountTestComponent(<Harness />);
    let framesRequested = 0;
    window.requestAnimationFrame = () => ++framesRequested;
    window.matchMedia = ((query: string) => ({ matches: query.includes("prefers-reduced-motion: reduce"), media: query })) as unknown as typeof window.matchMedia;
    try {
      const container = view.container.firstElementChild as HTMLDivElement;
      const target = container.firstElementChild as HTMLDivElement;
      Object.defineProperties(container, { clientHeight: { value: 600 }, scrollHeight: { value: 6000 } });

      await act(async () => controller.scrollToBottom("smooth"));
      assert.equal(container.scrollTop, 5400);
      assert.equal(controller.isAutoScrollingRef.current, false);

      container.scrollTop = 5400;
      target.getBoundingClientRect = () => ({ x: 0, y: -3000, top: -3000, bottom: -2900, left: 0, right: 100, width: 100, height: 100, toJSON: () => ({}) });
      let settled = 0;
      await act(async () => controller.scrollToMessage(target, () => { settled += 1; }));
      assert.equal(settled, 1);
      assert.notEqual(container.scrollTop, 5400);
      assert.equal(controller.isAutoScrollingRef.current, false);
      assert.equal(framesRequested, 0);
    } finally { await view.cleanup(); }
  });
});
