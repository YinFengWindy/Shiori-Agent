/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createParallaxLoop, type ParallaxPoint } from "./backdropParallax";

describe("createParallaxLoop", () => {
  function fakeFrames() {
    const queue = new Map<number, FrameRequestCallback>();
    let next = 1;
    let time = 0;
    return {
      requestFrame: (callback: FrameRequestCallback) => {
        queue.set(next, callback);
        return next++;
      },
      cancelFrame: (handle: number) => {
        queue.delete(handle);
      },
      /** Runs one frame; returns whether any callback ran. */
      tick() {
        const callbacks = [...queue.values()];
        queue.clear();
        time += 1000 / 60;
        callbacks.forEach((callback) => callback(time));
        return callbacks.length > 0;
      },
      get pending() {
        return queue.size;
      },
    };
  }

  it("runs frames only until settled, then stops (no idle frames)", () => {
    const frames = fakeFrames();
    const drawn: ParallaxPoint[] = [];
    const loop = createParallaxLoop({ apply: (point) => drawn.push(point), requestFrame: frames.requestFrame, cancelFrame: frames.cancelFrame });
    assert.equal(loop.running, false);
    loop.setTarget({ x: 0.5, y: 0.2 });
    assert.equal(loop.running, true);
    let count = 0;
    while (frames.tick()) count += 1;
    assert.ok(count > 10 && count < 120, `settled after ${count} frames`);
    assert.equal(loop.running, false);
    assert.equal(frames.pending, 0);
    assert.deepEqual(drawn.at(-1), { x: 0.5, y: 0.2 });
  });

  it("keeps one frame chain however many pointer moves arrive", () => {
    const frames = fakeFrames();
    const loop = createParallaxLoop({ apply: () => undefined, requestFrame: frames.requestFrame, cancelFrame: frames.cancelFrame });
    loop.setTarget({ x: 0.2, y: 0 });
    loop.setTarget({ x: 0.4, y: 0 });
    loop.setTarget({ x: 0.6, y: 0 });
    assert.equal(frames.pending, 1);
  });

  it("reset stops at once and draws the centre", () => {
    const frames = fakeFrames();
    const drawn: ParallaxPoint[] = [];
    const loop = createParallaxLoop({ apply: (point) => drawn.push(point), requestFrame: frames.requestFrame, cancelFrame: frames.cancelFrame });
    loop.setTarget({ x: 1, y: 1 });
    frames.tick();
    loop.reset();
    assert.equal(loop.running, false);
    assert.equal(frames.pending, 0);
    assert.deepEqual(drawn.at(-1), { x: 0, y: 0 });
  });
});
