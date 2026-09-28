import assert from "node:assert/strict";
import { test } from "node:test";
import {
  accountChannelLine, accountDeletionDescription, accountHeadline, accountName, accountStatus, accountStatusView,
  pendingAccountStatus, roleDeletionDescription,
} from "./accountPresentation";
import type { AccountSnapshot } from "./accountClient";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "Demo", avatarUrl: "", roleId: "role-1",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [] },
};

test("status uses live report and never presents a stopped provider as online", () => {
  assert.equal(accountStatus(account), "在线");
  assert.equal(accountStatus({ ...account, connection: "connecting" }), "连接中");
  assert.equal(accountStatus({ ...account, connection: "login_required" }), "需要登录");
  assert.equal(accountStatus({ ...account, connection: "error" }), "故障");
  assert.equal(accountStatus({ ...account, connection: "offline" }), "离线");
  assert.equal(accountStatus({ ...account, runtimeActive: false }), "离线");
});

test("status tone is green online, yellow while connecting or awaiting login, red on error, gray otherwise", () => {
  assert.deepEqual(accountStatusView(account), { label: "在线", tone: "success" });
  assert.equal(accountStatusView({ ...account, connection: "connecting" }).tone, "warning");
  assert.equal(accountStatusView({ ...account, connection: "login_required" }).tone, "warning");
  assert.equal(accountStatusView({ ...account, connection: "error" }).tone, "danger");
  assert.equal(accountStatusView({ ...account, connection: "unknown" }).tone, "muted");
  // A plugin that is not running cannot vouch for an online account.
  assert.deepEqual(accountStatusView({ ...account, runtimeActive: false }), { label: "离线", tone: "muted" });
  assert.deepEqual(pendingAccountStatus("disconnect"), { label: "正在断开", tone: "warning" });
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
