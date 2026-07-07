/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildChatImageHistoryKey,
  collectChatImageHistory,
  findChatImageHistoryEntry,
  findChatImageHistoryIndex,
  isChatImageAsset,
  resolveChatImageSelectionKey,
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
        historyKey: "message-1:0",
        path: "outputs/cover.png",
        messageId: "message-1",
        mediaIndex: 0,
        timestamp: null,
      },
      {
        historyKey: "message-2:0",
        path: "outputs/preview.webp",
        messageId: "message-2",
        mediaIndex: 0,
        timestamp: "2026-07-03T10:05:00.000Z",
      },
      {
        historyKey: "message-2:1",
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
        historyKey: "assistant-0:0",
        path: "outputs/cover.png",
        messageId: "assistant-0",
        mediaIndex: 0,
        timestamp: null,
      },
    ]);
  });

  it("ignores malformed non-string media entries instead of crashing the renderer", () => {
    const session = createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", 42 as unknown as string, null as unknown as string],
      },
    ]);

    assert.deepEqual(collectChatImageHistory(session), [
      {
        historyKey: "message-1:0",
        path: "outputs/cover.png",
        messageId: "message-1",
        mediaIndex: 0,
        timestamp: null,
      },
    ]);
  });
});

describe("buildChatImageHistoryKey", () => {
  it("keeps duplicate image paths distinct by message and media position", () => {
    assert.equal(buildChatImageHistoryKey("message-1", 0), "message-1:0");
  });
});

describe("resolveChatImageSelectionKey", () => {
  it("keeps the current selection when it is still in history", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/cover.png", "outputs/render.jpg"],
      },
    ]));

    assert.equal(resolveChatImageSelectionKey(history, "message-1:0"), "message-1:0");
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

    assert.equal(resolveChatImageSelectionKey(history, "message-1:9"), "message-1:1");
  });

  it("keeps the newest duplicate image selected by its own history key", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/render.jpg"],
      },
      {
        id: "message-2",
        role: "assistant",
        content: "second",
        media: ["outputs/render.jpg"],
      },
    ]));

    assert.equal(resolveChatImageSelectionKey(history, "message-2:0"), "message-2:0");
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

    assert.equal(findChatImageHistoryIndex(history, "message-1:1"), 1);
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

  it("distinguishes duplicate paths by history key", () => {
    const history = collectChatImageHistory(createSession([
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["outputs/render.jpg"],
      },
      {
        id: "message-2",
        role: "assistant",
        content: "second",
        media: ["outputs/render.jpg"],
      },
    ]));

    assert.equal(findChatImageHistoryIndex(history, "message-2:0"), 1);
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

    assert.deepEqual(findChatImageHistoryEntry(history, "message-1:1"), {
      historyKey: "message-1:1",
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

    assert.equal(findChatImageHistoryEntry(history, "unknown:0"), null);
  });
});
