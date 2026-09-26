import assert from "node:assert/strict";
import { it } from "node:test";
import { configuredApps, withConnection, withSavedApp, type FeishuApp } from "./accountConfig";

it("migrates a legacy Lark app exactly once while retaining its secret reference", () => {
  const legacy = { app_id: "cli_old", app_secret: "${LARK_SECRET}", domain: "lark" };
  const values = { ...legacy, accounts: [{ ...legacy }] };
  assert.deepEqual(configuredApps(values), [legacy]);
  assert.deepEqual(withSavedApp(values, { app_id: "cli_new", app_secret: "s", domain: "feishu" }), {
    app_id: "", app_secret: "", domain: "feishu", legacy_channel_ref: "lark:cli_old",
    accounts: [legacy, { app_id: "cli_new", app_secret: "s", domain: "feishu", connection_enabled: true, connection_revision: 1 }],
  });
});

it("disconnects and reconnects one app without replacing another app's secret", () => {
  const first: FeishuApp = { app_id: "cli_a", app_secret: "first", domain: "feishu", connection_enabled: true, connection_revision: 3 };
  const second: FeishuApp = { app_id: "cli_b", app_secret: "second", domain: "lark", connection_enabled: true, connection_revision: 5 };
  const disconnected = withConnection({ accounts: [first, second] }, "feishu:cli_a", false);
  assert.deepEqual(disconnected.accounts, [{ ...first, connection_enabled: false }, second]);
  const reconnected = withSavedApp(disconnected, first);
  assert.deepEqual(reconnected.accounts, [{ ...first, connection_revision: 4 }, second]);
});

it("keeps an account with a missing secret available for repair", () => {
  assert.deepEqual(configuredApps({ accounts: [
    { app_id: "cli_missing", app_secret: "", domain: "lark" },
  ] }), [{ app_id: "cli_missing", app_secret: "", domain: "lark" }]);
});

it("normalizes the former URL domain before clearing legacy fields", () => {
  const values = { app_id: "cli_old", app_secret: "${LARK_SECRET}", domain: "https://open.larksuite.com/" };
  assert.deepEqual(configuredApps(values), [{ app_id: "cli_old", app_secret: "${LARK_SECRET}", domain: "lark" }]);
});
