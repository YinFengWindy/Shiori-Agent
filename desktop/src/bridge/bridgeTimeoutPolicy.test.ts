import assert from "node:assert/strict";
import test from "node:test";
import { bridgeRequestTimeoutMs, bridgeTimeoutPolicy } from "./bridgeTimeoutPolicy.js";

test("bridge timeout policy keeps command classes explicit", () => {
  assert.equal(bridgeRequestTimeoutMs("health"), bridgeTimeoutPolicy.health);
  assert.equal(bridgeTimeoutPolicy.startup, 60_000);
  assert.equal(bridgeRequestTimeoutMs("roles.list"), bridgeTimeoutPolicy.defaultRequest);
  assert.equal(bridgeTimeoutPolicy.voiceRequest, 30_000);
  assert.equal(bridgeRequestTimeoutMs("voice.clone"), bridgeTimeoutPolicy.voiceRequest);
  assert.equal(bridgeRequestTimeoutMs("novelai.generate"), bridgeTimeoutPolicy.imageGeneration);
  assert.equal(bridgeRequestTimeoutMs("observation.analyze"), bridgeTimeoutPolicy.observation);
});
