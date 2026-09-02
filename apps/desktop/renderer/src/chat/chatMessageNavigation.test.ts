/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { watchForChatMessageTarget } from "./chatMessageNavigation";

type FakeElement = HTMLElement & { scrollIntoView: () => void };

function createHarness() {
  let target: FakeElement | null = null;
  let mutationCallback: (() => void) | null = null;
  const animationFrames: Array<() => void> = [];
  const timeouts: Array<() => void> = [];
  let cancelledFrames = 0;
  let clearedTimeouts = 0;
  let observed = false;
  let foundCount = 0;

  const stop = watchForChatMessageTarget({
    findTarget: () => target,
    onTarget: () => {
      foundCount += 1;
    },
    requestAnimationFrame: (callback) => {
      animationFrames.push(() => callback(0));
      return animationFrames.length;
    },
    cancelAnimationFrame: () => {
      cancelledFrames += 1;
    },
    setTimeout: (callback) => {
      timeouts.push(callback);
      return timeouts.length;
    },
    clearTimeout: () => {
      clearedTimeouts += 1;
    },
    observeMutations: (callback) => {
      observed = true;
      mutationCallback = callback;
      return () => {
        observed = false;
        mutationCallback = null;
      };
    },
  });

  return {
    animationFrames,
    createTarget: () => {
      target = { scrollIntoView: () => undefined } as FakeElement;
    },
    emitMutation: () => mutationCallback?.(),
    foundCount: () => foundCount,
    stop,
    timeouts,
    state: () => ({ cancelledFrames, clearedTimeouts, observed }),
  };
}

describe("watchForChatMessageTarget", () => {
  it("keeps waiting when the target mounts after the initial render", () => {
    const harness = createHarness();

    harness.animationFrames[0]!();
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const retry = harness.timeouts.shift();
      assert.ok(retry);
      retry();
    }
    assert.equal(harness.foundCount(), 0);

    harness.createTarget();
    harness.emitMutation();

    assert.equal(harness.foundCount(), 1);
    assert.deepEqual(harness.state(), {
      cancelledFrames: 0,
      clearedTimeouts: 1,
      observed: false,
    });
  });

  it("stops all retries after the navigation is cancelled", () => {
    const harness = createHarness();

    harness.stop();
    harness.createTarget();
    harness.emitMutation();
    for (const retry of harness.timeouts.splice(0)) {
      retry();
    }

    assert.equal(harness.foundCount(), 0);
    assert.deepEqual(harness.state(), {
      cancelledFrames: 1,
      clearedTimeouts: 0,
      observed: false,
    });
  });
});
