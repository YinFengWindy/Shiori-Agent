/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createParallaxLoop, parallaxTarget, parallaxTransforms, stepParallax, type ParallaxPoint } from "./backdropParallax";

const rect = { left: 100, top: 50, width: 800, height: 600 };

describe("parallaxTarget", () => {
  it("normalises the pointer around the centre and clamps outside", () => {
    assert.deepEqual(parallaxTarget(500, 350, rect), { x: 0, y: 0 });
    assert.deepEqual(parallaxTarget(900, 50, rect), { x: 1, y: -1 });
    assert.deepEqual(parallaxTarget(2000, -400, rect), { x: 1, y: -1 });
  });
});

describe("stepParallax", () => {
  it("covers the same distance per second at any frame rate", () => {
    let at60: ParallaxPoint = { x: 0, y: 0 };
    for (let frame = 0; frame < 6; frame += 1) at60 = stepParallax(at60, { x: 1, y: 0 }, 1000 / 60).point;
    let at30: ParallaxPoint = { x: 0, y: 0 };
    for (let frame = 0; frame < 3; frame += 1) at30 = stepParallax(at30, { x: 1, y: 0 }, 1000 / 30).point;
    assert.ok(Math.abs(at60.x - at30.x) < 1e-9);
  });

  it("snaps onto the target once close and reports settled", () => {
    assert.deepEqual(stepParallax({ x: 0.99, y: -0.99 }, { x: 1, y: -1 }, 16), { point: { x: 1, y: -1 }, settled: true });
    assert.equal(stepParallax({ x: 0, y: 0 }, { x: 1, y: 0 }, 16).settled, false);
  });

  it("does not leap after a long stall", () => {
    assert.deepEqual(
      stepParallax({ x: 0, y: 0 }, { x: 1, y: 0 }, 5000).point,
      stepParallax({ x: 0, y: 0 }, { x: 1, y: 0 }, 64).point,
    );
  });
});

describe("parallaxTransforms", () => {
  it("moves the background up to 12px against the pointer and the conversation 3px with it", () => {
    assert.deepEqual(parallaxTransforms({ x: 1, y: -1 }), {
      backdrop: "translate3d(-12.00px, 12.00px, 0)",
      foreground: "translate3d(3.00px, -3.00px, 0)",
    });
  });

  it("clears the transforms at the centre", () => {
    assert.deepEqual(parallaxTransforms({ x: 0, y: 0 }), { backdrop: "", foreground: "" });
  });
});

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
