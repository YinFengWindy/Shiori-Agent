/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getChatScrollTargetTop,
  getChatSessionRestoreScrollTop,
  rememberChatSessionScrollState,
  type ChatSessionScrollState,
} from "./chatScrollController";

function createScrollStateCache() {
  return new Map<string, ChatSessionScrollState>();
}

describe("rememberChatSessionScrollState", () => {
  it("keeps a shared container's position under the previous session key", () => {
    const cache = createScrollStateCache();

    rememberChatSessionScrollState(cache, "role:mira", 180, 1_000, 400);
    rememberChatSessionScrollState(cache, "role:luna", 520, 1_200, 400);

    assert.equal(
      getChatSessionRestoreScrollTop(cache.get("role:mira")!, 1_000, 400),
      180,
    );
    assert.equal(
      getChatSessionRestoreScrollTop(cache.get("role:luna")!, 1_200, 400),
      520,
    );
  });

  it("keeps a session anchored to the bottom when its content grows", () => {
    const cache = createScrollStateCache();

    rememberChatSessionScrollState(cache, "role:mira", 576, 1_000, 400);

    assert.equal(
      getChatSessionRestoreScrollTop(cache.get("role:mira")!, 1_400, 400),
      1_000,
    );
  });
});

describe("getChatScrollTargetTop", () => {
  it("centers a mounted message inside the scroll container", () => {
    assert.equal(
      getChatScrollTargetTop({
        currentScrollTop: 100,
        containerTop: 40,
        containerHeight: 500,
        targetTop: 740,
        targetHeight: 100,
        maxTop: 2_000,
      }),
      600,
    );
  });

  it("clamps a centered target to the scrollable range", () => {
    assert.equal(
      getChatScrollTargetTop({
        currentScrollTop: 100,
        containerTop: 40,
        containerHeight: 500,
        targetTop: 60,
        targetHeight: 100,
        maxTop: 1_000,
      }),
      0,
    );
  });
});
