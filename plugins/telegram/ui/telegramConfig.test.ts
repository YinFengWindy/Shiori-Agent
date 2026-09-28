import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginConfigSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { telegramBots, withTelegramBot } from "./telegramConfig";

const config = (values: Record<string, unknown>): PluginConfigSnapshot => ({ pluginId: "telegram", schema: null, values, envStatus: {} });

test("a Bot is saved for its own role and the old single Token is never taken over", () => {
  const saved = config({ token: "123:old", bots: [{ ref: "second", token: "456:new", enabled: true, role_id: "mira" }] });
  assert.deepEqual(telegramBots(saved).map((bot) => bot.ref), ["second"]);
  const changed = withTelegramBot(saved, "second", "456:replacement", true, "mira");
  assert.equal(changed.token, "123:old");
  const added = withTelegramBot(config(changed), "third", "789:t", true, "other");
  assert.deepEqual((added.bots as Array<{ ref: string; role_id?: string }>).map((bot) => [bot.ref, bot.role_id]),
    [["second", "mira"], ["third", "other"]]);
});

test("another role's or an ownerless Bot cannot be changed", () => {
  const saved = config({ bots: [
    { ref: "owned", token: "123:a", enabled: true, role_id: "mira" },
    { ref: "old", token: "456:b", enabled: true },
  ] });
  assert.throws(() => withTelegramBot(saved, "owned", undefined, false, "other"), /另一个角色/);
  assert.throws(() => withTelegramBot(saved, "old", undefined, true, "other"), /未归属/);
});
