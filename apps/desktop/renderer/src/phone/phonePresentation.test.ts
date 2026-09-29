import assert from "node:assert/strict";
import { test } from "node:test";
import type { AccountSnapshot } from "@shiori/plugin-sdk";
import type { PhoneConversation } from "./phoneClient";
import { accountConversations, phoneApps, phoneConversationPreview } from "./phonePresentation";

const account = (id: string, patch: Partial<AccountSnapshot> = {}): AccountSnapshot => ({
  id, pluginId: "qq", platform: "qq", platformAccountId: id, configRef: id,
  displayName: "", avatarUrl: "", roleId: "mira",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [] },
  ...patch,
});

const conversation = (threadId: string, patch: Partial<PhoneConversation> = {}): PhoneConversation => ({
  threadId, accountId: "qq:1", channel: "qq", chatType: "private", displayName: threadId, isUserChat: false,
  lastMessage: { role: "user", content: "在吗", timestamp: "2026-09-29T10:00:00+08:00", hasMedia: false, senderName: null },
  ...patch,
});

test("home screen shows every account of the role, offline ones marked, named by their channel", () => {
  const Icon = () => null;
  const channels: Record<string, { label: string; Icon?: typeof Icon }> = {
    qq: { label: "QQ", Icon },
    feishu: { label: "飞书 / Lark" },
  };
  const apps = phoneApps([
    account("qq:1"),
    account("feishu:4", { pluginId: "feishu", platform: "feishu", runtimeActive: false }),
    account("qq:3", { roleId: "other" }),
    account("telegram:2", { pluginId: "telegram", platform: "telegram", connection: "offline" }),
  ], "mira", (pluginId) => channels[pluginId]);

  assert.deepEqual(apps, [
    { accountId: "qq:1", label: "QQ", Icon, offline: false },
    // The registered channel label, as the role page shows it, not the platform id.
    { accountId: "feishu:4", label: "飞书 / Lark", Icon: undefined, offline: true },
    // A plugin whose UI registered no channel label is word-cased, never shown raw.
    { accountId: "telegram:2", label: "Telegram", Icon: undefined, offline: true },
  ]);
});

test("an app lists only its account's conversations, in the bridge's newest-first order", () => {
  const rows = [
    conversation("newest"),
    conversation("elsewhere", { accountId: "telegram:2" }),
    conversation("orphan", { accountId: null }),
    conversation("older"),
  ];

  assert.deepEqual(accountConversations(rows, "qq:1").map((row) => row.threadId), ["newest", "older"]);
});

test("group previews name the other sender; the role's own and private messages do not", () => {
  const group = conversation("g", { chatType: "group" });
  assert.equal(
    phoneConversationPreview({ ...group, lastMessage: { ...group.lastMessage, content: "**开黑**吗", senderName: "阿花" } }),
    "阿花：开黑吗",
  );
  assert.equal(
    phoneConversationPreview({ ...group, lastMessage: { ...group.lastMessage, role: "assistant", content: "来了" } }),
    "来了",
  );
  const privateChat = conversation("p");
  assert.equal(
    phoneConversationPreview({ ...privateChat, lastMessage: { ...privateChat.lastMessage, content: "", hasMedia: true, senderName: "小明" } }),
    "[图片]",
  );
});
