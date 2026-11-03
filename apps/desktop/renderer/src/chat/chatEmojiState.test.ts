/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {  insertEmojiIntoChatDraft } from "./chatEmojiState";

describe("insertEmojiIntoChatDraft", () => {

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
