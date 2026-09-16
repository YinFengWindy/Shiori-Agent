import assert from "node:assert/strict";
import { test } from "node:test";
import { PluginBackgroundMethods } from "./pluginBackgroundMethods";

test("duplicate registration retains the existing handler and retired callbacks cannot reply", async () => {
  const methods = new PluginBackgroundMethods();
  let complete!: () => void;
  const gate = new Promise<void>((resolve) => { complete = resolve; });
  await methods.register("sync", async () => { await gate; return "first"; }, async () => {});
  await assert.rejects(methods.register("sync", () => "second", async () => {}), { code: "plugin_method_exists" });
  let current = true;
  const replies: unknown[] = [];
  const pending = methods.dispatch({ id: "event", type: "event", method: "plugin.demo.__request", payload: { name: "sync", request_id: "request" } },
    () => current, async (reply) => { replies.push(reply); });
  current = false;
  methods.clear();
  complete();
  await pending;
  assert.deepEqual(replies, []);
});
