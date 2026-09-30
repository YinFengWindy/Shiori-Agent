import assert from "node:assert/strict";
import { test } from "node:test";
import type { PhoneMessage } from "./phoneClient";
import { phoneChatTimeline } from "./phoneChatTimeline";

const at = (id: string, minute: number, listened = false): PhoneMessage => ({
  id, seq: null, sender: "other", senderId: "42", senderName: "阿花", senderIsUser: false, senderAvatarPath: null, mentions: [], quote: null, content: id, media: [],
  timestamp: `2026-09-30T10:${String(minute).padStart(2, "0")}:00+08:00`, listened,
});

test("listening records and the conversation interleave by time", () => {
  const timeline = phoneChatTimeline(
    { messages: [at("问", 1), at("答", 5)], hasMore: false },
    { messages: [at("闲聊", 0, true), at("插话", 3, true), at("后来", 9, true)], hasMore: false },
  );
  assert.deepEqual(timeline.messages.map((message) => message.id), ["闲聊", "问", "插话", "答", "后来"]);
  assert.equal(timeline.hasMore, false);
  assert.equal(timeline.olderFrom, null);
});

test("only the span both streams loaded shows; the stream bounding it loads its older page next", () => {
  // The listening page reaches back to 10:02; the conversation's only to 10:05.
  const conversation = { messages: [at("答", 5)], hasMore: true };
  const listening = { messages: [at("插话", 2, true), at("后来", 9, true)], hasMore: true };
  const partial = phoneChatTimeline(conversation, listening);
  assert.deepEqual(partial.messages.map((message) => message.id), ["答", "后来"]);
  assert.equal(partial.olderFrom, "conversation");

  // Once the conversation's older page is in, the held-back record shows in its place.
  const caughtUp = phoneChatTimeline({ messages: [at("问", 1), at("答", 5)], hasMore: false }, listening);
  assert.deepEqual(caughtUp.messages.map((message) => message.id), ["插话", "答", "后来"]);
  assert.equal(caughtUp.olderFrom, "listening");
});
