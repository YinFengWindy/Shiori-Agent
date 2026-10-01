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


test("a background RPC reply retains structured upstream diagnostics", async () => {
  const { PluginBridgeError } = await import("@shiori/plugin-sdk");
  const methods = new PluginBackgroundMethods();
  await methods.register("sync", async () => { throw new PluginBridgeError("配置同步失败", "config_sync_failed", { detail: "missing asset token=private-value" }); }, async () => undefined);
  let response: Record<string, unknown> | undefined;
  await methods.dispatch({ id: "1", type: "event", method: "plugin.demo.__request", payload: { name: "sync", request_id: "r" } },
    () => true, async (value) => { response = value; });
  assert.match(JSON.stringify(response), /config_sync_failed|missing asset/);
  assert.doesNotMatch(JSON.stringify(response), /private-value/);
  assert.deepEqual(response, { request_id: "r", error: { code: "config_sync_failed", message: "配置同步失败", details: { detail: "missing asset token=***" } } });
});
