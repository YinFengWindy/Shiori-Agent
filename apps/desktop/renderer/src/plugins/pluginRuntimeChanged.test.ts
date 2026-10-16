import assert from "node:assert/strict";
import { test } from "node:test";
import { pluginContextReplaced, pluginRuntimeChanged, pluginRosterChanged } from "./pluginRuntimeChanged";

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

test("an in-generation reload replaces only the reloaded plugins' contexts (#857)", () => {
  const event = { id: "save", type: "event" as const, method: "plugins.reloaded", payload: { generation: 1, plugin_ids: ["novelai", "story"] } };
  assert.equal(pluginRuntimeChanged(event), false);
  assert.equal(pluginRosterChanged(event), true);
  assert.equal(pluginContextReplaced(event, "novelai"), true);
  assert.equal(pluginContextReplaced(event, "story"), true);
  assert.equal(pluginContextReplaced(event, "desktop_pet"), false);
  assert.equal(pluginContextReplaced({ ...event, method: "runtime.applied", payload: { changed: true } }, "desktop_pet"), true);
});
