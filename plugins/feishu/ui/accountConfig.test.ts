import assert from "node:assert/strict";
import { it } from "node:test";
import { configuredApps, withSavedApp } from "./accountConfig";

it("migrates a legacy Lark app exactly once while retaining its secret reference", () => {
  const legacy = { app_id: "cli_old", app_secret: "${LARK_SECRET}", domain: "lark" };
  const values = { ...legacy, accounts: [{ ...legacy }] };
  assert.deepEqual(configuredApps(values), [legacy]);
  assert.deepEqual(withSavedApp(values, { app_id: "cli_new", app_secret: "s", domain: "feishu" }), {
    app_id: "", app_secret: "", domain: "feishu", accounts: [legacy, { app_id: "cli_new", app_secret: "s", domain: "feishu" }],
  });
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
