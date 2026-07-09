/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { commonChatEmojis, insertEmojiIntoChatDraft } from "./chatEmojiState";

describe("commonChatEmojis", () => {
  it("keeps a fixed lightweight desktop emoji set", () => {
    assert.equal(commonChatEmojis.length, 24);
    assert.deepEqual(commonChatEmojis.slice(0, 4), ["😀", "😁", "😂", "🤣"]);
  });
});

describe("insertEmojiIntoChatDraft", () => {
  it("appends emoji when no selection is provided", () => {
    const result = insertEmojiIntoChatDraft("hello", "😀");

    assert.equal(result.value, "hello😀");
    assert.equal(result.selectionStart, 7);
    assert.equal(result.selectionEnd, 7);
  });

  it("inserts emoji at the current caret position", () => {
    const result = insertEmojiIntoChatDraft("hello world", "✨", 5, 5);

    assert.equal(result.value, "hello✨ world");
    assert.equal(result.selectionStart, 6);
    assert.equal(result.selectionEnd, 6);
  });

  it("replaces the current selection with the picked emoji", () => {
    const result = insertEmojiIntoChatDraft("hello world", "🔥", 6, 11);

    assert.equal(result.value, "hello 🔥");
    assert.equal(result.selectionStart, 8);
    assert.equal(result.selectionEnd, 8);
  });

  it("clamps invalid selection ranges before inserting", () => {
    const result = insertEmojiIntoChatDraft("chat", "❤️", 99, -5);

    assert.equal(result.value, "❤️");
    assert.equal(result.selectionStart, 2);
    assert.equal(result.selectionEnd, 2);
  });
});
