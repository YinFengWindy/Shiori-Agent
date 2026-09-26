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
