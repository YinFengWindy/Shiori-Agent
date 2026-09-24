/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  advanceChatMessageEnterState,
  chatMessageEnterWindowMs,
  initialChatMessageEnterState,
  isChatMessageEntering,
  pruneChatMessageEnterState,
} from "./chatMessageEnterState";

describe("chat message enter animation gating", () => {
  const mounted = advanceChatMessageEnterState(initialChatMessageEnterState, "role:a", ["m1", "m2"], 1000);

  it("does not animate the rows present when a session is first shown", () => {
    assert.equal(isChatMessageEntering(mounted, "m1", 1000), false);
    assert.equal(isChatMessageEntering(mounted, "m2", 1000), false);
  });

  it("animates a message appended after mount", () => {
    const next = advanceChatMessageEnterState(mounted, "role:a", ["m1", "m2", "m3"], 2000);
    assert.equal(isChatMessageEntering(next, "m3", 2000), true);
  });

  it("does not animate on a session switch", () => {
    const switched = advanceChatMessageEnterState(mounted, "role:b", ["b1", "b2"], 2000);
    assert.equal(isChatMessageEntering(switched, "b1", 2000), false);
    assert.equal(isChatMessageEntering(switched, "b2", 2000), false);
  });

  it("does not animate history pagination prepended above the known rows", () => {
    const paged = advanceChatMessageEnterState(mounted, "role:a", ["old1", "old2", "m1", "m2"], 2000);
    assert.equal(isChatMessageEntering(paged, "old1", 2000), false);
    assert.equal(isChatMessageEntering(paged, "old2", 2000), false);
  });

  it("does not replay when virtualization remounts a row after its window", () => {
    const appended = advanceChatMessageEnterState(mounted, "role:a", ["m1", "m2", "m3"], 2000);
    // Scrolled away and back: same keys, later time.
    const remounted = advanceChatMessageEnterState(appended, "role:a", ["m1", "m2", "m3"], 2000 + chatMessageEnterWindowMs + 5000);
    assert.equal(remounted, appended);
    assert.equal(isChatMessageEntering(remounted, "m3", 2000 + chatMessageEnterWindowMs + 5000), false);
  });

  it("keeps the same state object when nothing new arrived (streaming updates)", () => {
    assert.equal(advanceChatMessageEnterState(mounted, "role:a", ["m1", "m2"], 5000), mounted);
  });
});

describe("pruneChatMessageEnterState", () => {
  it("closes finished windows so a later remount renders without the animation", () => {
    const appended = advanceChatMessageEnterState(
      advanceChatMessageEnterState(initialChatMessageEnterState, "role:a", ["m1"], 0),
      "role:a",
      ["m1", "m2"],
      100,
    );
    const pruned = pruneChatMessageEnterState(appended, 100 + chatMessageEnterWindowMs);
    assert.equal(pruned.entering.has("m2"), false);
    assert.equal(pruneChatMessageEnterState(pruned, 99999), pruned);
  });
});
