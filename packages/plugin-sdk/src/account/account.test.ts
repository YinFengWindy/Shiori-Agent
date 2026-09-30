import assert from "node:assert/strict";
import { test } from "node:test";
import { accountStatus, accountStatusView, pendingAccountStatus, type AccountSnapshot } from "./account";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "Demo", avatarUrl: "", roleId: "role-1",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, blockedSenderIds: [] },
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
});
