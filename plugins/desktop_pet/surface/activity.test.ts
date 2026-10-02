import assert from "node:assert/strict";
import test from "node:test";
import { resolvePetActivityState, transitionPetActivity } from "./activity";

test("Codex pet activity keeps needs-input above blocked, ready, and running", () => {
  assert.equal(resolvePetActivityState({ active: "running", failed: "failed", ready: "review", waiting: "waiting" }), "waiting");
});

test("role activity preserves priority and acknowledges a proactive message once", () => {
  const running = transitionPetActivity({}, { roleId: "a", sessionKey: "a-main", phase: "running", notify: false });
  assert.equal(running.state, "running");
  const needsInput = transitionPetActivity(running.activities, { roleId: "a", sessionKey: "a-secondary", phase: "waiting", notify: true });
  assert.equal(needsInput.state, "waiting");
  assert.equal(needsInput.showNotification, true);
  const repeated = transitionPetActivity(needsInput.activities, { roleId: "a", sessionKey: "a-secondary", phase: "waiting", notify: true });
  assert.equal(repeated.showNotification, false);
  const blocked = transitionPetActivity(needsInput.activities, { roleId: "a", sessionKey: "a-main", phase: "failed", notify: false });
  assert.equal(blocked.state, "waiting");
  const reviewed = transitionPetActivity(blocked.activities, { roleId: "a", sessionKey: "a-secondary", phase: "review", notify: false });
  assert.equal(reviewed.state, "failed");
});
