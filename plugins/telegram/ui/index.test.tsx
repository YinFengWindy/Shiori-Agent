import assert from "node:assert/strict";
import { test } from "node:test";
import telegramUi from "./index";

test("Telegram contributes only role-page account controls, no settings page", () => {
  assert.equal(telegramUi.pluginId, "telegram");
  assert.equal(telegramUi.settingsSection, undefined);
  assert.equal(telegramUi.accountDetail?.label, "Telegram");
  assert.ok(telegramUi.accountDetail?.component);
});
