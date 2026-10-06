import assert from "node:assert/strict";
import test from "node:test";
import { bridgeRequestTimeoutMs, bridgeTimeoutPolicy } from "./bridgeTimeoutPolicy.js";

test("bridge timeout policy keeps command classes explicit", () => {
  assert.equal(bridgeRequestTimeoutMs("health"), bridgeTimeoutPolicy.health);
  assert.equal(bridgeRequestTimeoutMs("runtime.apply"), null);
  assert.equal(bridgeRequestTimeoutMs("chat.context.compact"), null);
  assert.equal(bridgeRequestTimeoutMs("plugins.communication.services.call"), null);
  assert.equal(bridgeRequestTimeoutMs("plugins.communication.services.call", 20_000), null);
  assert.equal(bridgeRequestTimeoutMs("plugins.communication.services.list", 20_000), 20_000);
  assert.equal(bridgeTimeoutPolicy.startup, 60_000);
  assert.equal(bridgeRequestTimeoutMs("roles.list"), bridgeTimeoutPolicy.defaultRequest);
  assert.equal(bridgeRequestTimeoutMs("plugin.sample.slow", 300_000), 300_000);
  assert.equal(bridgeRequestTimeoutMs("plugin.sample.slow"), bridgeTimeoutPolicy.defaultRequest);
  assert.throws(() => bridgeRequestTimeoutMs("plugin.sample.slow", -1));
  assert.equal(bridgeRequestTimeoutMs("runtime.apply", 1), null);
});
