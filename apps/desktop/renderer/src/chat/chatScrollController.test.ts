/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getChatSessionRestoreScrollTop,
  getChatSessionResetScrollBehavior,
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

describe("getChatSessionResetScrollBehavior", () => {
  it("jumps to the bottom on the first session load", () => {
    assert.equal(getChatSessionResetScrollBehavior("", "role:mira"), "auto");
  });

  it("smoothly moves to the bottom when switching between loaded sessions", () => {
    assert.equal(getChatSessionResetScrollBehavior("role:shiori", "role:mira"), "smooth");
  });
});
