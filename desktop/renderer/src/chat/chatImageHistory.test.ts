/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  collectChatImageHistory,
  findChatImageHistoryEntry,
  findChatImageHistoryIndex,
  isChatImageAsset,
  resolveChatImageSelection,
} from "./chatImageHistory";
import type { SessionPayload } from "../shared/types";

function createSession(messages: SessionPayload["messages"]): SessionPayload {
  return {
    key: "session-1",
    created_at: "2026-07-03T10:00:00.000Z",
    updated_at: "2026-07-03T10:05:00.000Z",
    last_consolidated: 0,
    metadata: {},
    messages,
  };
}

describe("isChatImageAsset", () => {
  it("accepts supported image media paths", () => {
    assert.equal(isChatImageAsset("outputs/mira-1.PNG?download=1"), true);
  });

  it("rejects non-image media paths", () => {
    assert.equal(isChatImageAsset("outputs/mira-1.txt"), false);
  });
});

describe("collectChatImageHistory", () => {
  it("collects only chat images and preserves their order", () => {
    const session = createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", "outputs/readme.txt"],
      },
      {
        id: "message-2",
        role: "assistant",
        content: "second",
        timestamp: "2026-07-03T10:05:00.000Z",
        media: ["outputs/preview.webp", "outputs/render.jpg"],
      },
    ]);

    assert.deepEqual(collectChatImageHistory(session), [
      {
        path: "outputs/cover.png",
        messageId: "message-1",
        mediaIndex: 0,
        timestamp: null,
      },
      {
        path: "outputs/preview.webp",
        messageId: "message-2",
        mediaIndex: 0,
        timestamp: "2026-07-03T10:05:00.000Z",
      },
      {
        path: "outputs/render.jpg",
        messageId: "message-2",
        mediaIndex: 1,
        timestamp: "2026-07-03T10:05:00.000Z",
      },
    ]);
  });

  it("falls back to the rendered message key when the source message has no id", () => {
    const session = createSession([
      {
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png"],
      },
    ]);

    assert.deepEqual(collectChatImageHistory(session), [
      {
        path: "outputs/cover.png",
        messageId: "assistant-0",
        mediaIndex: 0,
        timestamp: null,
      },
    ]);
  });
});

describe("resolveChatImageSelection", () => {
  it("keeps the current selection when it is still in history", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", "outputs/render.jpg"],
      },
    ]));

    assert.equal(resolveChatImageSelection(history, "outputs/cover.png"), "outputs/cover.png");
  });

  it("falls back to the newest image when the current selection is missing", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", "outputs/render.jpg"],
      },
    ]));

    assert.equal(resolveChatImageSelection(history, "outputs/unknown.png"), "outputs/render.jpg");
  });
});

describe("findChatImageHistoryIndex", () => {
  it("returns the selected image index", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", "outputs/render.jpg"],
      },
    ]));

    assert.equal(findChatImageHistoryIndex(history, "outputs/render.jpg"), 1);
  });

  it("falls back to the newest image index when the selection is empty", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", "outputs/render.jpg"],
      },
    ]));

    assert.equal(findChatImageHistoryIndex(history, ""), 1);
  });
});

describe("findChatImageHistoryEntry", () => {
  it("returns the selected entry so callers can locate the source message", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", "outputs/render.jpg"],
      },
    ]));

    assert.deepEqual(findChatImageHistoryEntry(history, "outputs/render.jpg"), {
      path: "outputs/render.jpg",
      messageId: "message-1",
      mediaIndex: 1,
      timestamp: null,
    });
  });

  it("returns null when the selected image is not in history", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png"],
      },
    ]));

    assert.equal(findChatImageHistoryEntry(history, "outputs/unknown.png"), null);
  });
});
