import assert from "node:assert/strict";
import { test } from "node:test";
import { PluginCommunicationLifetime } from "./pluginCommunicationLifetime";

test("disposal immediately rejects pending work and rejects late admission", async () => {
  const lifetime = new PluginCommunicationLifetime();
  const pending = lifetime.wait(new Promise(() => {}));
  lifetime.dispose();
  await assert.rejects(pending, { code: "plugin_unavailable" });
  assert.throws(() => lifetime.assertActive(), { code: "plugin_unavailable" });
});

test("completed operations preserve backend errors and results", async () => {
  const lifetime = new PluginCommunicationLifetime();
  assert.equal(await lifetime.wait(Promise.resolve(5)), 5);
  const failure = new Error("failed");
  await assert.rejects(lifetime.wait(Promise.reject(failure)), (error) => error === failure);
  lifetime.dispose();
});
