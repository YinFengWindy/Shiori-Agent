import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginConfigSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { telegramBots, withTelegramBot } from "./telegramConfig";

test("old Token becomes one legacy bot without duplicating it", () => {
  const config: PluginConfigSnapshot = { pluginId: "telegram", schema: null,
    values: { token: "123:old", bots: [{ ref: "second", token: "456:new", enabled: true }] }, envStatus: {} };
  assert.deepEqual(telegramBots(config).map((bot) => bot.ref), ["legacy", "second"]);
  const changed = withTelegramBot(config, "second", "456:replacement", true);
  assert.equal(changed.token, "");
  assert.deepEqual((changed.bots as Array<{ ref: string; token: string }>).map((bot) => [bot.ref, bot.token]),
    [["legacy", "123:old"], ["second", "456:replacement"]]);
});
