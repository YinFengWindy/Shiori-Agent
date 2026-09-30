import assert from "node:assert/strict";
import { test } from "node:test";
import type { PhoneConversation, PhoneMessage } from "./phoneClient";
import {
  mergePhoneMessages, phoneChatItems, phoneQuoteItem, phoneSeparatorTime, withLiveConversations,
} from "./phoneChatPresentation";

test("a quote goes by its sender's name, else the ID; only a long text collapses", () => {
  const short = phoneQuoteItem({ senderId: "7", name: null, content: "看", media: [] });
  const long = phoneQuoteItem({ senderId: "7", name: "阿花", content: "一\n二\n三", media: [] });
  assert.deepEqual([short.label, short.collapsible], ["7", false]);
  assert.deepEqual([long.label, long.collapsible], ["阿花", true]);
});

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

const now = new Date("2026-09-29T12:00:00+08:00");

test("the role's messages sit right without a name; others sit left under their name, the bound user marked", () => {
  const items = phoneChatItems([
    message("a"),
    message("b", { senderName: null, senderId: "7" }),
    message("c", { senderName: "主人", senderIsUser: true }),
    message("d", { sender: "role", senderName: null, senderId: null }),
  ], now).filter((item) => item.kind === "message");
  assert.deepEqual(items.map(({ side, senderLabel, isUser }) => ({ side, senderLabel, isUser })), [
    { side: "left", senderLabel: "阿花", isUser: false },
    // No name recorded: the platform ID stands in.
    { side: "left", senderLabel: "7", isUser: false },
    { side: "left", senderLabel: "主人", isUser: true },
    { side: "right", senderLabel: null, isUser: false },
  ]);
});

test("a message's mentions lead it as @name, the member ID when no name is known", () => {
  const [item] = phoneChatItems([
    message("a", { mentions: [{ id: "10001", name: "小栞" }, { id: "99", name: null }] }),
  ], now).filter((line) => line.kind === "message");
  assert.deepEqual(item?.mentionLabels, ["@小栞", "@99"]);
});

test("a time separator opens the chat and follows every pause longer than five minutes", () => {
  const items = phoneChatItems([
    message("a", { timestamp: "2026-09-28T21:00:00+08:00" }),
    message("b", { timestamp: "2026-09-28T21:04:00+08:00" }),
    message("c", { timestamp: "not a time" }),
    // Measured from b, the last readable time.
    message("d", { timestamp: "2026-09-28T21:08:00+08:00" }),
    message("e", { timestamp: "2026-09-29T11:30:00+08:00" }),
  ], now);
  assert.deepEqual(items.map((item) => (item.kind === "time" ? `[${item.label}]` : item.key)), [
    `[${phoneSeparatorTime("2026-09-28T21:00:00+08:00", now)}]`, "a", "b", "c", "d",
    `[${phoneSeparatorTime("2026-09-29T11:30:00+08:00", now)}]`, "e",
  ]);
});

test("separator time is the clock today and the day plus the clock before", () => {
  const today = new Date(2026, 8, 29, 9, 5);
  const yesterday = new Date(2026, 8, 28, 21, 30);
  assert.equal(phoneSeparatorTime(today.toISOString(), new Date(2026, 8, 29, 12)), "09:05");
  assert.equal(phoneSeparatorTime(yesterday.toISOString(), new Date(2026, 8, 29, 12)), "昨天 21:30");
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
