import assert from "node:assert/strict";
import { test } from "node:test";
import { pluginRuntimeChanged } from "./pluginRuntimeChanged";

test("no-op runtime writes preserve contexts, real publication and transport reconnect replace them", () => {
  const event = { id: "test", type: "event" as const, method: "runtime.applied", payload: { changed: false } };
  assert.equal(pluginRuntimeChanged(event), false);
  assert.equal(pluginRuntimeChanged({ ...event, payload: { changed: true } }), true);
  assert.equal(pluginRuntimeChanged({ ...event, method: "bridge.exit" }), true);
  assert.equal(pluginRuntimeChanged({ ...event, method: "bridge.ready" }), true);
  assert.equal(pluginRuntimeChanged({ ...event, method: "chat.done" }), false);
});
