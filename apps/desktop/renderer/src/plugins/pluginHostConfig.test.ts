import assert from "node:assert/strict";
import { test } from "node:test";
import { deferred } from "@shiori/plugin-sdk/testing";
import type { PluginConfigValues } from "@shiori/plugin-sdk";
import { PluginBridgeError, type PluginBridgeClient } from "./pluginBridgeClient";
import { createPluginConfigChanges } from "./pluginConfigChanges";
import { createPluginHostConfig } from "./pluginHostConfig";

/** A bridge over in-memory plugin tables that records every set; sets can be held or rejected. */
function fakeConfigBridge(tables: Record<string, PluginConfigValues>) {
  const sets: Array<{ pluginId: string; values: PluginConfigValues }> = [];
  let hold: Promise<void> | null = null;
  let reject: Error | null = null;
  const client: Pick<PluginBridgeClient, "getConfig" | "setConfig"> = {
    async getConfig(pluginId) {
      return { pluginId, schema: null, values: { ...tables[pluginId] }, envStatus: {} };
    },
    async setConfig(pluginId, values) {
      sets.push({ pluginId, values });
      if (hold) await hold;
      if (reject) throw reject;
      tables[pluginId] = { ...values };
      return { pluginId, values: { ...values }, envStatus: {}, generation: sets.length };
    },
  };
  return {
    client, sets,
    holdSets(gate: Promise<void> | null) { hold = gate; },
    rejectSets(error: Error | null) { reject = error; },
  };
}

test("host.config reads and saves only its own plugin's table, merging each patch over the stored values", async () => {
  const tables = { novelai: { nsfw_enabled: false, default_model: "curated" }, other: { secret: "x" } };
  const bridge = fakeConfigBridge(tables);
  const config = createPluginHostConfig("novelai", bridge.client, createPluginConfigChanges());

  assert.deepEqual(await config.get(), { nsfw_enabled: false, default_model: "curated" });
  assert.deepEqual(await config.save({ nsfw_enabled: true }), { nsfw_enabled: true, default_model: "curated" });
  assert.deepEqual(bridge.sets, [{ pluginId: "novelai", values: { nsfw_enabled: true, default_model: "curated" } }]);
  assert.deepEqual(tables.other, { secret: "x" });
});

test("saves run one at a time, so two quick patches both survive", async () => {
  const bridge = fakeConfigBridge({ novelai: { a: 0, b: 0 } });
  const config = createPluginHostConfig("novelai", bridge.client, createPluginConfigChanges());
  const gate = deferred<void>();
  bridge.holdSets(gate.promise);
  const first = config.save({ a: 1 });
  const second = config.save({ b: 1 });
  // Let the first save reach the held set before releasing it.
  await new Promise((resolve) => setTimeout(resolve, 0));
  bridge.holdSets(null);
  gate.resolve();
  assert.deepEqual(await first, { a: 1, b: 0 });
  assert.deepEqual(await second, { a: 1, b: 1 });
});

test("a stored save is published to that plugin's subscribers; a rejected one publishes nothing and fails the caller", async () => {
  const bridge = fakeConfigBridge({ novelai: {}, other: {} });
  const changes = createPluginConfigChanges();
  const config = createPluginHostConfig("novelai", bridge.client, changes);
  const heard: PluginConfigValues[] = [];
  const otherPlugin: PluginConfigValues[] = [];
  const unsubscribe = config.subscribe((values) => heard.push(values));
  changes.subscribe("other", (values) => otherPlugin.push(values));

  await config.save({ add_quality_tags: true });
  assert.deepEqual(heard, [{ add_quality_tags: true }]);

  bridge.rejectSets(new PluginBridgeError("undesired_content_preset 必须是整数", "plugin_config_invalid"));
  await assert.rejects(config.save({ undesired_content_preset: "x" }), /必须是整数/);
  assert.equal(heard.length, 1);
  bridge.rejectSets(null);
  // A failure does not wedge the queue.
  await config.save({ undesired_content_preset: 1 });
  assert.equal(heard.length, 2);

  unsubscribe();
  await config.save({ add_quality_tags: false });
  assert.equal(heard.length, 2);
  assert.deepEqual(otherPlugin, []);
});
