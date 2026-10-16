import assert from "node:assert/strict";
import { test } from "node:test";
import { reloadedPluginIds } from "./pluginsReloaded";

test("only a plugins.reloaded event names reloaded plugins, ignoring malformed ids (#857)", () => {
  const event = (method: string, payload: Record<string, unknown>) => ({ id: "e", type: "event" as const, method, payload });
  assert.deepEqual(reloadedPluginIds(event("plugins.reloaded", { generation: 1, plugin_ids: ["novelai", 7, "story"] })), ["novelai", "story"]);
  assert.deepEqual(reloadedPluginIds(event("plugins.reloaded", { generation: 1 })), []);
  assert.deepEqual(reloadedPluginIds(event("plugins.changed", { plugin_ids: ["novelai"] })), []);
});
