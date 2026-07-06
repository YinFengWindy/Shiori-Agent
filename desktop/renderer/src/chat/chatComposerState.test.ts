/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildOptimisticUserChatMessage,
  canSubmitChatMessage,
  normalizeChatAttachmentPaths,
  summarizeChatReplyContent,
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

  it("includes reply metadata on optimistic user messages", () => {
    assert.deepEqual(
      buildOptimisticUserChatMessage("  继续  ", [], {
        messageId: "message-1",
        sender: "Mira",
        content: "她停顿了一下。",
        preview: "她停顿了一下。",
      }),
      {
        role: "user",
        content: "继续",
        metadata: {
          reply_to_message_id: "message-1",
          reply_to_content: "她停顿了一下。",
          reply_to_sender: "Mira",
        },
      },
    );
  });
});

describe("summarizeChatReplyContent", () => {
  it("compacts whitespace and truncates long reply previews", () => {
    const preview = summarizeChatReplyContent(`  ${"a".repeat(120)}\n next `);

    assert.equal(preview, `${"a".repeat(96)}...`);
  });
});
