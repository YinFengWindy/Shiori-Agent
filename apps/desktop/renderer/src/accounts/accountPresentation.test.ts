import assert from "node:assert/strict";
import { test } from "node:test";
import { accountDeletionDescription, accountHeadline, accountName, accountStatus } from "./accountPresentation";
import type { AccountSnapshot } from "./accountClient";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "Demo", avatarUrl: "", roleId: null, pluginEnabled: true,
  runtimeActive: true, connection: "online", capabilities: [], knownCapabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [], groupRules: [] },
};

test("status uses live report and never presents a stopped provider as online", () => {
  assert.equal(accountStatus(account), "在线");
  assert.equal(accountStatus({ ...account, connection: "connecting" }), "连接中");
  assert.equal(accountStatus({ ...account, connection: "login_required" }), "需要登录");
  assert.equal(accountStatus({ ...account, connection: "error" }), "故障");
  assert.equal(accountStatus({ ...account, connection: "offline" }), "离线");
  assert.equal(accountStatus({ ...account, pluginEnabled: false }), "离线");
  assert.equal(accountStatus({ ...account, runtimeActive: false }), "离线");
});

test("account names fall back to the platform ID and the delete text names the account", () => {
  assert.equal(accountName(account), "Demo");
  assert.equal(accountName({ ...account, displayName: "" }), "101");
  assert.equal(accountHeadline({ ...account, displayName: "" }), "demo · 101");
  assert.equal(accountDeletionDescription(null), "");
  assert.match(accountDeletionDescription(account), /^“demo · Demo” /);
});
