import assert from "node:assert/strict";
import { test } from "node:test";
import { pluginRuntimeChanged, pluginRosterChanged } from "./pluginRuntimeChanged";

test("no-op runtime writes preserve contexts, real publication and transport reconnect replace them", () => {
  const event = { id: "test", type: "event" as const, method: "runtime.applied", payload: { changed: false } };
  assert.equal(pluginRuntimeChanged(event), false);
  assert.equal(pluginRuntimeChanged({ ...event, payload: { changed: true } }), true);
  assert.equal(pluginRuntimeChanged({ ...event, method: "bridge.exit" }), true);
  assert.equal(pluginRuntimeChanged({ ...event, method: "bridge.ready" }), true);
  assert.equal(pluginRuntimeChanged({ ...event, method: "chat.done" }), false);
});


test("readiness refreshes only the roster, while publications refresh both", () => {
  const event = { id: "ready", type: "event" as const, method: "plugins.changed", payload: { generation: 7, plugin_id: "demo", kind: "ui" } };
  assert.equal(pluginRuntimeChanged(event), false);
  assert.equal(pluginRosterChanged(event), true);
  assert.equal(pluginRosterChanged({ ...event, method: "runtime.applied" }), true);
  assert.equal(pluginRosterChanged({ ...event, method: "plugin.demo.changed" }), false);
});
