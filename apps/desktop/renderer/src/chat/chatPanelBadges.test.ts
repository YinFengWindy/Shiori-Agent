/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clearViewedChatPanelBadge,
  emptyChatPanelBadges,
  markChatPanelUpdates,
  shouldBadgeChatPanelToggle,
} from "./chatPanelBadges.js";

const closed = { open: false, mode: "tasks" as const };

describe("chat panel badges", () => {
  it("marks a new image and a new thought while the panel is closed, and dots the toggle", () => {
    const badges = markChatPanelUpdates(emptyChatPanelBadges, { newImage: true, newThought: true }, closed);
    assert.deepEqual(badges, { images: true, status: true });
    assert.equal(shouldBadgeChatPanelToggle(badges, false), true);
    assert.equal(shouldBadgeChatPanelToggle(badges, true), false);
  });

  it("does not mark the segment the user is already looking at", () => {
    const badges = markChatPanelUpdates(emptyChatPanelBadges, { newImage: true, newThought: true }, { open: true, mode: "images" });
    assert.deepEqual(badges, { images: false, status: true });
  });

  it("marks an open panel's other segment instead of switching to it", () => {
    const badges = markChatPanelUpdates(emptyChatPanelBadges, { newImage: true, newThought: false }, { open: true, mode: "tasks" });
    assert.deepEqual(badges, { images: true, status: false });
  });

  it("clears only the segment being viewed, and only while open", () => {
    const both = { images: true, status: true };
    assert.equal(clearViewedChatPanelBadge(both, { open: false, mode: "images" }), both);
    assert.deepEqual(clearViewedChatPanelBadge(both, { open: true, mode: "images" }), { images: false, status: true });
    assert.deepEqual(clearViewedChatPanelBadge(both, { open: true, mode: "status" }), { images: true, status: false });
    assert.equal(clearViewedChatPanelBadge(both, { open: true, mode: "tasks" }), both);
  });

  it("returns the same object when nothing changes", () => {
    assert.equal(markChatPanelUpdates(emptyChatPanelBadges, { newImage: false, newThought: false }, closed), emptyChatPanelBadges);
    const marked = { images: true, status: false };
    assert.equal(markChatPanelUpdates(marked, { newImage: true, newThought: false }, closed), marked);
    assert.equal(shouldBadgeChatPanelToggle(emptyChatPanelBadges, false), false);
  });
});
