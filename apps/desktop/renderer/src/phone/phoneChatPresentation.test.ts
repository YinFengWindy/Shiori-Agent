import assert from "node:assert/strict";
import { test } from "node:test";
import type { PhoneConversation, PhoneMessage } from "./phoneClient";
import {
  mergePhoneMessages, withLiveConversations,
} from "./phoneChatPresentation";

const message = (id: string, patch: Partial<PhoneMessage> = {}): PhoneMessage => ({
  id, seq: null, sender: "other", senderId: "42", senderName: "阿花", senderIsUser: false,
  senderAvatarPath: null, mentions: [], quote: null, content: id, media: [], timestamp: "2026-09-29T10:00:00+08:00", listened: false,
  ...patch,
});

const conversation = (threadId: string, timestamp: string): PhoneConversation => ({
  threadId, accountId: "qq:1", channel: "qq", chatType: "group", displayName: threadId, avatarPath: null,
  isUserChat: false, listeningSupported: false,
  lastMessage: { role: "user", content: "在吗", timestamp, hasMedia: false, senderName: null },
});

test("merging messages skips ones already shown and keeps the same list when nothing is new", () => {
  const shown = [message("b"), message("c")];
  assert.deepEqual(mergePhoneMessages([message("a")], shown).map((item) => item.id), ["a", "b", "c"]);
  assert.deepEqual(mergePhoneMessages(shown, [message("c"), message("d")]).map((item) => item.id), ["b", "c", "d"]);
  assert.equal(mergePhoneMessages(shown, [message("b")]), shown);
});

test("live rows update their conversation, add new ones and reorder newest first", () => {
  const loaded = [conversation("group", "2026-09-29T10:00:00+08:00"), conversation("private", "2026-09-29T09:00:00+08:00")];
  const rows = withLiveConversations(loaded, [
    conversation("private", "2026-09-29T11:00:00+08:00"),
    conversation("new", "2026-09-29T10:30:00+08:00"),
    // Older than what the list already shows: ignored.
    conversation("group", "2026-09-29T08:00:00+08:00"),
  ]);
  assert.deepEqual(rows.map((row) => [row.threadId, row.lastMessage.timestamp]), [
    ["private", "2026-09-29T11:00:00+08:00"],
    ["new", "2026-09-29T10:30:00+08:00"],
    ["group", "2026-09-29T10:00:00+08:00"],
  ]);
  assert.equal(withLiveConversations(loaded, []), loaded);
});
