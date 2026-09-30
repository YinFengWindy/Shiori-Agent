import assert from "node:assert/strict";
import { test } from "node:test";
import {
  accountChannelLabel, accountChannelLine, accountDeletionDescription, accountHeadline, accountName, roleDeletionDescription,
} from "./accountPresentation";
import type { AccountSnapshot } from "@shiori/plugin-sdk";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "Demo", avatarUrl: "", roleId: "role-1",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, blockedSenderIds: [] },
};

test("the channel line names the channel and the platform ID", () => {
  assert.equal(accountChannelLine("QQ", account), "QQ · 101");
});

test("account names fall back to the platform ID and the delete text names the account", () => {
  assert.equal(accountName(account), "Demo");
  assert.equal(accountName({ ...account, displayName: "" }), "101");
  assert.equal(accountHeadline({ ...account, displayName: "" }), "demo · 101");
  assert.equal(accountDeletionDescription(null), "");
  assert.match(accountDeletionDescription(account), /^“demo · Demo” /);
});

test("role deletion text lists the accounts deleted with the role, or why they are unknown", () => {
  assert.equal(roleDeletionDescription("Mira", { accounts: [], error: "", status: "ready" }), "“Mira” 删除后会移除角色会话与相关素材。");
  assert.match(roleDeletionDescription("Mira", { accounts: [], error: "", status: "loading" }), /正在读取关联账号/);
  assert.equal(
    roleDeletionDescription("Mira", { accounts: [account, { ...account, platform: "qq", displayName: "" }], error: "", status: "ready" }),
    "“Mira” 删除后会移除角色会话与相关素材。以下账号会一并删除：demo · Demo、qq · 101。",
  );
  assert.match(roleDeletionDescription("Mira", { accounts: [], error: "bridge down", status: "error" }), /账号列表读取失败，暂不能确认删除范围/);
});

test("a channel is named by its plugin's registered label, else its word-cased id", () => {
  assert.equal(accountChannelLabel("feishu", { label: "飞书 / Lark" }), "飞书 / Lark");
  assert.equal(accountChannelLabel("tool_loop_guard", undefined), "Tool Loop Guard");
});
