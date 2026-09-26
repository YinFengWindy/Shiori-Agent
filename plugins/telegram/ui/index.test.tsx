import assert from "node:assert/strict";
import { test } from "node:test";
import telegramUi from "./index";

test("Telegram settings expose the host account list and platform detail", () => {
  assert.equal(telegramUi.pluginId, "telegram");
  assert.equal(telegramUi.settingsSection?.kind, "component");
  assert.ok(telegramUi.accountDetail?.component);
});
