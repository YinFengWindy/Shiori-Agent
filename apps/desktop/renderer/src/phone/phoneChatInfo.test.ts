import assert from "node:assert/strict";
import { test } from "node:test";
import { memberDraftDirty, noteDraftDirty, phoneChatInfoSections, phoneChatSummaryRows, phoneMemberEntryOf, phoneSubpageBack } from "./phoneChatInfo";
import type { PhoneChatItem } from "./phoneChatPresentation";
import type { PhoneMessage } from "./phoneClient";

type MessageItem = Extract<PhoneChatItem, { kind: "message" }>;

const item = (patch: Partial<PhoneMessage>, isUser = false): MessageItem => {
  const message: PhoneMessage = {
    id: "m", seq: 1, sender: "other", senderId: "42", senderName: "阿花", senderIsUser: isUser,
    content: "", media: [], timestamp: "", ...patch,
  };
  return { kind: "message", key: "m", message, side: message.sender === "role" ? "right" : "left", senderLabel: null, isUser };
};

const group = { isUserChat: false, chatType: "group" } as const;

test("external chats get the four blocks in order; the user's own chat gets none", () => {
  assert.deepEqual(phoneChatInfoSections(group), [
    { id: "summary", title: "群信息" },
    { id: "members", title: "群成员" },
    { id: "note", title: "群笔记" },
    { id: "activity", title: "最近动态" },
  ]);
  // A stranger's private chat is external as well, titled for a chat.
  assert.deepEqual(
    phoneChatInfoSections({ isUserChat: false, chatType: "private" }).map(({ id, title }) => `${id}:${title}`),
    ["summary:聊天信息", "members:成员", "note:笔记", "activity:最近动态"],
  );
  assert.deepEqual(phoneChatInfoSections({ isUserChat: true, chatType: "private" }), []);
});

test("the summary names the group or the other person, the channel and the carrying account", () => {
  const app = { label: "QQ", accountName: "小栞" };
  assert.deepEqual(phoneChatSummaryRows({ chatType: "group", displayName: "摸鱼群" }, app), [
    { label: "群名", value: "摸鱼群" }, { label: "渠道", value: "QQ" }, { label: "经由账号", value: "小栞" },
  ]);
  assert.equal(phoneChatSummaryRows({ chatType: "private", displayName: "小明" }, app)[0]?.label, "对方");
});

test("an avatar opens a member profile only for another, identified sender in an external chat", () => {
  assert.equal(phoneMemberEntryOf(item({}), group), "42");
  // The user has no member profile.
  assert.equal(phoneMemberEntryOf(item({ senderIsUser: true }, true), group), null);
  assert.equal(phoneMemberEntryOf(item({ sender: "role", senderId: null }), group), null);
  assert.equal(phoneMemberEntryOf(item({ senderId: null }), group), null);
  assert.equal(phoneMemberEntryOf(item({}), { isUserChat: true, chatType: "private" }), null);
});

test("a profile goes back to where it was opened from; the info page back to the chat", () => {
  assert.deepEqual(phoneSubpageBack({ kind: "member", senderId: "42", from: "info" }), { kind: "info" });
  assert.equal(phoneSubpageBack({ kind: "member", senderId: "42", from: "chat" }), null);
  assert.equal(phoneSubpageBack({ kind: "info" }), null);
});

test("a draft is dirty only when it would store something else (the bridge trims)", () => {
  assert.equal(noteDraftDirty("abc", "abc"), false);
  // Saving "abc\n" over "abc" stores "abc" again: nothing left to save.
  assert.equal(noteDraftDirty("abc\n", "abc"), false);
  assert.equal(noteDraftDirty("abcd", "abc"), true);
  const stored = { brief: "爱开黑", profile: "## 印象" };
  assert.equal(memberDraftDirty({ ...stored }, stored), false);
  assert.equal(memberDraftDirty({ brief: " 爱开黑 ", profile: "## 印象\n" }, stored), false);
  assert.equal(memberDraftDirty({ ...stored, brief: "爱睡觉" }, stored), true);
  assert.equal(memberDraftDirty({ ...stored, profile: "" }, stored), true);
});
