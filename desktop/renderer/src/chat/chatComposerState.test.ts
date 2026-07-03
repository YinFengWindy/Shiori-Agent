/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildOptimisticUserChatMessage,
  canSubmitChatMessage,
  normalizeChatAttachmentPaths,
} from "./chatComposerState";

describe("normalizeChatAttachmentPaths", () => {
  it("trims entries and deduplicates repeated selections", () => {
    assert.deepEqual(
      normalizeChatAttachmentPaths(["  D:\\files\\note.md  ", "D:\\files\\note.md", "", "D:\\files\\pic.png"]),
      ["D:\\files\\note.md", "D:\\files\\pic.png"],
    );
  });
});

describe("canSubmitChatMessage", () => {
  it("allows attachment-only sends", () => {
    assert.equal(canSubmitChatMessage("", ["D:\\files\\note.md"]), true);
  });

  it("rejects empty text and empty attachments", () => {
    assert.equal(canSubmitChatMessage("   ", []), false);
  });
});

describe("buildOptimisticUserChatMessage", () => {
  it("includes media on optimistic user messages", () => {
    assert.deepEqual(
      buildOptimisticUserChatMessage("  hello  ", ["D:\\files\\note.md", "D:\\files\\pic.png"]),
      {
        role: "user",
        content: "hello",
        media: ["D:\\files\\note.md", "D:\\files\\pic.png"],
      },
    );
  });
});
